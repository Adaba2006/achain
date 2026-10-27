import copy, hashlib, json, os, time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

REWARD = 50
MIN_FEE = 1
MAX_TXS = 100             # per block and in the pending pool

INITIAL_BITS = 16         # same strength as 4 hex zeros
MIN_BITS, MAX_BITS = 8, 40
ADJUST_INTERVAL = 5       # re-check difficulty every 5 blocks
TARGET_BLOCK_TIME = 2     # seconds

GENESIS = {"index": 0, "time": 0, "txs": [], "prev_hash": "0",
           "nonce": 0, "bits": INITIAL_BITS}

BLOCK_FIELDS = {"index", "time", "txs", "prev_hash", "nonce", "bits"}
TX_FIELDS = {"from", "to", "amount", "fee", "nonce", "sig"}
COINBASE_FIELDS = {"from", "to", "amount", "height"}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def make_hash(block):
    return sha(canon(block))

def address_of(pub_hex):
    return sha(bytes.fromhex(pub_hex))[:40]

def is_int(x):
    return type(x) is int

def is_num(x):
    return type(x) in (int, float)

def meets_target(hash_hex, bits):
    """True if the hash has at least `bits` leading zero bits."""
    return int(hash_hex, 16) < (1 << (256 - bits))

def expected_bits(blocks, i):
    """The difficulty block i MUST use, computed from the blocks before it."""
    prev_bits = blocks[i - 1]["bits"]
    if i < 2 * ADJUST_INTERVAL or i % ADJUST_INTERVAL != 0:
        return prev_bits
    first, last = blocks[i - ADJUST_INTERVAL], blocks[i - 1]
    span = last["time"] - first["time"]
    expected = (ADJUST_INTERVAL - 1) * TARGET_BLOCK_TIME
    if span < expected / 2:
        return min(prev_bits + 1, MAX_BITS)     # blocks too fast: harder
    if span > expected * 2:
        return max(prev_bits - 1, MIN_BITS)     # blocks too slow: easier
    return prev_bits

def chain_work(blocks):
    """Total work in a validated chain (each bit doubles the work)."""
    return sum(1 << b["bits"] for b in blocks[1:])

class Wallet:
    def __init__(self, sk=None):
        self.sk = sk or Ed25519PrivateKey.generate()
        self.pub = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        self.address = address_of(self.pub)

    def send(self, to, amount, nonce, fee=MIN_FEE):
        body = {"from": self.pub, "to": to, "amount": amount,
                "fee": fee, "nonce": nonce}
        body["sig"] = self.sk.sign(canon(body)).hex()
        return body

    def save(self, path, password):
        pem = self.sk.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password.encode()))
        with open(path, "wb") as f:
            f.write(pem)

    @staticmethod
    def load(path, password):
        with open(path, "rb") as f:
            return Wallet(serialization.load_pem_private_key(f.read(), password.encode()))

def apply_tx(balances, nonces, tx):
    """Validate one transaction, update balances, return the fee it pays."""
    if not isinstance(tx, dict) or set(tx) != TX_FIELDS:
        raise ValueError("bad transaction fields")
    if not (is_int(tx["amount"]) and tx["amount"] > 0):
        raise ValueError("bad amount")
    if not (is_int(tx["fee"]) and tx["fee"] >= MIN_FEE):
        raise ValueError("fee below minimum")
    if not (is_int(tx["nonce"]) and tx["nonce"] > 0):
        raise ValueError("bad nonce value")
    if not isinstance(tx["to"], str):
        raise ValueError("bad receiver")
    body = {k: v for k, v in tx.items() if k != "sig"}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["from"])).verify(
            bytes.fromhex(tx["sig"]), canon(body))
    except (InvalidSignature, ValueError, KeyError, TypeError):
        raise ValueError("bad signature")
    sender = address_of(tx["from"])
    if tx["nonce"] != nonces.get(sender, 0) + 1:
        raise ValueError("bad nonce (replay or gap)")
    total = tx["amount"] + tx["fee"]
    if balances.get(sender, 0) < total:
        raise ValueError("insufficient funds")
    balances[sender] -= total
    balances[tx["to"]] = balances.get(tx["to"], 0) + tx["amount"]
    nonces[sender] = tx["nonce"]
    return tx["fee"]

def _validate(blocks):
    if not blocks or blocks[0] != GENESIS:
        raise ValueError("bad genesis")
    balances, nonces = {}, {}
    for i in range(1, len(blocks)):
        b, prev = blocks[i], blocks[i - 1]
        if set(b) != BLOCK_FIELDS:
            raise ValueError(f"block {i}: bad fields")
        if b["index"] != i:
            raise ValueError(f"block {i}: bad index")
        if b["prev_hash"] != make_hash(prev):
            raise ValueError(f"block {i}: broken link")
        if b["bits"] != expected_bits(blocks, i):
            raise ValueError(f"block {i}: wrong difficulty")
        if not meets_target(make_hash(b), b["bits"]):
            raise ValueError(f"block {i}: proof of work missing")
        t = b["time"]
        if not (is_num(t) and prev["time"] <= t <= time.time() + 7200):
            raise ValueError(f"block {i}: bad timestamp")
        txs = b["txs"]
        if not isinstance(txs, list) or not 1 <= len(txs) <= MAX_TXS + 1:
            raise ValueError(f"block {i}: bad transaction count")
        cb = txs[0]
        if (not isinstance(cb, dict) or set(cb) != COINBASE_FIELDS
                or cb["from"] != "COINBASE" or cb["height"] != i
                or not isinstance(cb["to"], str) or not is_int(cb["amount"])):
            raise ValueError(f"block {i}: bad coinbase")
        fees = 0
        for tx in txs[1:]:
            try:
                fees += apply_tx(balances, nonces, tx)
            except ValueError as e:
                raise ValueError(f"block {i}: {e}")
        if cb["amount"] != REWARD + fees:
            raise ValueError(f"block {i}: coinbase must be reward plus fees")
        balances[cb["to"]] = balances.get(cb["to"], 0) + cb["amount"]
    return balances, nonces

def validate(blocks):
    """Full re-check from genesis. Malformed data becomes ValueError, never a crash."""
    try:
        return _validate(blocks)
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError("malformed data")

class Chain:
    def __init__(self, blocks=None):
        self.blocks = blocks if blocks else [copy.deepcopy(GENESIS)]
        self.balances, self.nonces = validate(self.blocks)
        self.pending = []

    def add_tx(self, tx):
        if len(self.pending) >= MAX_TXS:
            raise ValueError("pending pool full")
        bal, non = copy.deepcopy(self.balances), copy.deepcopy(self.nonces)
        for p in self.pending:
            apply_tx(bal, non, p)
        apply_tx(bal, non, tx)          # raises if invalid
        self.pending.append(tx)

    def mine(self, miner_address):
        i = len(self.blocks)
        bits = expected_bits(self.blocks, i)
        fees = sum(p["fee"] for p in self.pending)
        coinbase = {"from": "COINBASE", "to": miner_address,
                    "amount": REWARD + fees, "height": i}
        block = {"index": i, "time": time.time(), "txs": [coinbase] + self.pending,
                 "prev_hash": make_hash(self.blocks[-1]), "nonce": 0, "bits": bits}
        while not meets_target(make_hash(block), bits):
            block["nonce"] += 1
        candidate = self.blocks + [block]
        self.balances, self.nonces = validate(candidate)
        self.blocks = candidate
        self.pending = []
        return block

    def adopt(self, blocks):
        """Take a peer's chain only if it is fully valid AND has more total work."""
        if not isinstance(blocks, list):
            return False
        bal, non = validate(blocks)     # raises ValueError if invalid
        if chain_work(blocks) <= chain_work(self.blocks):
            return False
        self.blocks, self.balances, self.nonces = blocks, bal, non
        self.pending = []               # simple approach: drop the pool
        return True

def save_chain(chain, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(chain.blocks, f)
    os.replace(tmp, path)               # avoids a half-written file

def load_chain(path):
    if os.path.exists(path):
        with open(path) as f:
            return Chain(json.load(f))  # re-validated, never trusted
    return Chain()