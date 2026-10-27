import functools, hmac, json, os, re, sys, threading, time
from collections import defaultdict, deque
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify

from auth import get_token
from chaincore import load_chain, save_chain

MAX_BODY = 256 * 1024                  # largest request body accepted
MAX_CHAIN_BYTES = 5 * 1024 * 1024      # largest chain downloaded from a peer
MAX_PEERS = 16
RATE_LIMIT = 100                       # requests per minute per client address
ADDRESS_RE = re.compile(r"[0-9a-f]{40}")

port = int(sys.argv[1])
chain_path = f"chain_{port}.json"
peers_path = f"peers_{port}.json"
TOKEN = get_token()

chain = load_chain(chain_path)
lock = threading.Lock()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
hits = defaultdict(deque)

# ---------- peers ----------
def clean_peer(url):
    """Return a normalised peer URL, or None if it is not acceptable."""
    if not isinstance(url, str) or len(url) > 200:
        return None
    try:
        u = urlparse(url)
        u.port                          # raises ValueError on a bad port
    except ValueError:
        return None
    ok = (u.scheme in ("http", "https") and u.hostname and not u.username
          and not u.password and u.path in ("", "/") and not u.query
          and not u.fragment)
    return f"{u.scheme}://{u.netloc}" if ok else None

def load_peers():
    try:
        with open(peers_path) as f:
            found = {clean_peer(p) for p in json.load(f)}
        return {p for p in found if p}
    except (OSError, ValueError, TypeError):
        return set()

def save_peers():
    tmp = peers_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(peers), f)
    os.replace(tmp, peers_path)

def fetch_chain(peer):
    """Download a peer's chain, refusing redirects and oversized answers."""
    with requests.get(peer + "/chain", timeout=10, stream=True,
                      allow_redirects=False) as r:
        if r.status_code != 200:
            raise ValueError("bad status from peer")
        size, parts = 0, []
        for part in r.iter_content(65536):
            size += len(part)
            if size > MAX_CHAIN_BYTES:
                raise ValueError("peer chain too large")
            parts.append(part)
    return json.loads(b"".join(parts))

peers = load_peers()

# ---------- protections ----------
@app.before_request
def rate_limit():
    now = time.time()
    q = hits[request.remote_addr]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return jsonify(error="rate limit exceeded"), 429
    q.append(now)

@app.errorhandler(413)
def too_big(e):
    return jsonify(error="request too large"), 413

def need_token(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        sent = request.headers.get("X-Token", "")
        if not hmac.compare_digest(sent.encode(), TOKEN.encode()):
            return jsonify(error="unauthorized"), 401
        return fn(*args, **kwargs)
    return wrapper

# ---------- public endpoints ----------
@app.get("/chain")
def get_chain():
    with lock:
        return jsonify(chain.blocks)

@app.get("/account/<address>")
def account(address):
    with lock:
        return jsonify(balance=chain.balances.get(address, 0),
                       next_nonce=chain.nonces.get(address, 0) + 1)

@app.post("/tx")
def new_tx():
    tx = request.get_json(silent=True)
    with lock:
        try:
            chain.add_tx(tx)
        except (ValueError, KeyError, TypeError) as e:
            return jsonify(error=str(e)), 400
    return jsonify(ok=True), 201

# ---------- operator endpoints (token required) ----------
@app.post("/mine/<address>")
@need_token
def mine(address):
    if not ADDRESS_RE.fullmatch(address):
        return jsonify(error="bad address"), 400
    with lock:
        block = chain.mine(address)
        save_chain(chain, chain_path)
    return jsonify(index=block["index"], txs=len(block["txs"]), bits=block["bits"])

@app.get("/peers")
@need_token
def list_peers():
    return jsonify(peers=sorted(peers))

@app.post("/peers")
@need_token
def add_peer():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    url = clean_peer(body.get("url"))
    if url is None:
        return jsonify(error="bad peer url"), 400
    if url not in peers and len(peers) >= MAX_PEERS:
        return jsonify(error="too many peers"), 400
    peers.add(url)
    save_peers()
    return jsonify(peers=sorted(peers))

@app.post("/sync")
@need_token
def sync():
    adopted = False
    for p in list(peers):
        try:
            theirs = fetch_chain(p)
            with lock:
                if chain.adopt(theirs):
                    save_chain(chain, chain_path)
                    adopted = True
        except (requests.RequestException, ValueError):
            continue                    # unreachable or invalid peer: ignore
    with lock:
        return jsonify(length=len(chain.blocks), adopted=adopted)

if __name__ == "__main__":
    print("Admin token is stored in node_token.txt (treat it like a password)")
    app.run(host="127.0.0.1", port=port)   # local only