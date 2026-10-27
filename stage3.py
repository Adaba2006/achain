import hashlib, json, time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

DIFFICULTY = 4

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def make_hash(block):
    return sha(canon(block))

class Wallet:
    def __init__(self):
        self.sk = Ed25519PrivateKey.generate()
        self.pub = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        self.address = sha(bytes.fromhex(self.pub))[:40]

    def send(self, to, amount, nonce):
        body = {"from": self.pub, "to": to, "amount": amount, "nonce": nonce}
        body["sig"] = self.sk.sign(canon(body)).hex()
        return body

def apply_tx(balances, nonces, tx):
    if tx["from"] == "COINBASE":                       # only used in block 0
        balances[tx["to"]] = balances.get(tx["to"], 0) + tx["amount"]
        return
    if not isinstance(tx["amount"], int) or tx["amount"] <= 0:
        raise ValueError("bad amount")
    body = {k: v for k, v in tx.items() if k != "sig"}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["from"])).verify(
            bytes.fromhex(tx["sig"]), canon(body))
    except (InvalidSignature, ValueError, KeyError):
        raise ValueError("bad signature")
    sender = sha(bytes.fromhex(tx["from"]))[:40]
    if tx["nonce"] != nonces.get(sender, 0) + 1:
        raise ValueError("bad nonce (replay or gap)")
    if balances.get(sender, 0) < tx["amount"]:
        raise ValueError("insufficient funds")
    balances[sender] -= tx["amount"]
    balances[tx["to"]] = balances.get(tx["to"], 0) + tx["amount"]
    nonces[sender] = tx["nonce"]

def mine_block(index, txs, prev_hash):
    block = {"index": index, "time": time.time(), "txs": txs,
             "prev_hash": prev_hash, "nonce": 0}
    while not make_hash(block).startswith("0" * DIFFICULTY):
        block["nonce"] += 1
    return block

def validate(chain):
    balances, nonces = {}, {}
    for i, block in enumerate(chain):
        if not make_hash(block).startswith("0" * DIFFICULTY):
            raise ValueError(f"block {i}: proof of work missing")
        if i == 0:
            if block["prev_hash"] != "0":
                raise ValueError("bad genesis")
        elif block["prev_hash"] != make_hash(chain[i - 1]):
            raise ValueError(f"block {i}: broken link")
        for tx in block["txs"]:
            if tx["from"] == "COINBASE" and i != 0:
                raise ValueError(f"block {i}: coinbase only allowed in block 0")
            try:
                apply_tx(balances, nonces, tx)
            except ValueError as e:
                raise ValueError(f"block {i}: {e}")
    return balances

# ---------- demo ----------
alice, bob, carol, mallory = Wallet(), Wallet(), Wallet(), Wallet()
names = {alice.address: "alice", bob.address: "bob", carol.address: "carol"}

def check(label, chain):
    try:
        bal = validate(chain)
        print(label, "-> VALID", {names.get(a, a[:6]): v for a, v in bal.items()})
    except ValueError as e:
        print(label, "-> REJECTED:", e)

# honest chain: alice starts with 100
chain = [mine_block(0, [{"from": "COINBASE", "to": alice.address, "amount": 100}], "0")]
tx1 = alice.send(bob.address, 30, 1)
chain.append(mine_block(1, [tx1], make_hash(chain[-1])))
tx2 = bob.send(carol.address, 10, 1)
chain.append(mine_block(2, [tx2], make_hash(chain[-1])))
check("honest chain ", chain)

# attack 1: attacker edits bob's signed transaction and re-mines the block
forged = dict(tx2); forged["amount"] = 25
check("forged amount", chain[:2] + [mine_block(2, [forged], make_hash(chain[1]))])

# attack 2: mallory signs with her own key but claims to be alice
stolen = mallory.send(mallory.address, 50, 1)
stolen["from"] = alice.pub
check("stolen coins ", chain[:2] + [mine_block(2, [stolen], make_hash(chain[1]))])

# attack 3: replay alice's old transaction
check("replayed tx  ", chain + [mine_block(3, [tx1], make_hash(chain[-1]))])

# attack 4: alice tries to spend more than she has
big = alice.send(bob.address, 1000, 2)
check("overspend    ", chain + [mine_block(3, [big], make_hash(chain[-1]))])