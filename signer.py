import getpass, re, sys
from flask import Flask, request, jsonify
from chaincore import Wallet, MIN_FEE

WALLET_FILE = sys.argv[1] if len(sys.argv) > 1 else "alice.pem"
MAX_AMOUNT = 500    # hard limit per transaction, enforced by the signer itself

wallet = Wallet.load(WALLET_FILE, getpass.getpass("Wallet password: "))
print("Signer ready. Address:", wallet.address)
app = Flask(__name__)

@app.get("/pubkey")
def pubkey():
    return jsonify(pub=wallet.pub, address=wallet.address)

@app.post("/sign")
def sign():
    req = request.get_json(silent=True) or {}
    to, amount, fee, nonce = (req.get(k) for k in ("to", "amount", "fee", "nonce"))
    ints_ok = all(type(x) is int for x in (amount, fee, nonce))
    if not (isinstance(to, str) and re.fullmatch(r"[0-9a-f]{40}", to) and ints_ok):
        return jsonify(error="malformed request"), 400
    if amount <= 0 or fee < MIN_FEE or nonce <= 0:
        return jsonify(error="invalid values"), 400
    if amount > MAX_AMOUNT:
        return jsonify(error=f"over signer limit of {MAX_AMOUNT}"), 403
    print(f"\nSIGN REQUEST\n  to:     {to}\n  amount: {amount}\n  fee:    {fee}\n  nonce:  {nonce}")
    if input("Approve? (y/N): ").strip().lower() != "y":
        print("Denied.")
        return jsonify(error="denied by owner"), 403
    print("Signed.")
    return jsonify(wallet.send(to, amount, nonce, fee))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=6000, threaded=False)   # local only