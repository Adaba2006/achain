import argparse, re, sys, requests
from auth import headers

SIGNER = "http://127.0.0.1:6000"

def die(msg):
    print("error:", msg)
    sys.exit(1)

def call(method, url, **kw):
    try:
        return requests.request(method, url, timeout=120, **kw)
    except requests.RequestException:
        die(f"cannot reach {url} (is it running?)")

def my_address():
    r = call("GET", SIGNER + "/pubkey")
    return r.json()["address"]

def main():
    p = argparse.ArgumentParser(description="Command line wallet (keys stay in signer.py)")
    p.add_argument("--node", default="http://127.0.0.1:5000")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("address", help="show your address")
    b = sub.add_parser("balance", help="show a balance (yours by default)")
    b.add_argument("address", nargs="?")
    s = sub.add_parser("send", help="send coins")
    s.add_argument("to")
    s.add_argument("amount", type=int)
    s.add_argument("--fee", type=int, default=1)
    sub.add_parser("mine", help="mine one block, reward goes to you")

    a = p.parse_args()
    node = a.node.rstrip("/")

    if a.cmd == "address":
        print(my_address())

    elif a.cmd == "balance":
        addr = a.address or my_address()
        j = call("GET", f"{node}/account/{addr}").json()
        print(f"balance: {j['balance']}  (next nonce: {j['next_nonce']})")

    elif a.cmd == "send":
        if not re.fullmatch(r"[0-9a-f]{40}", a.to):
            die("recipient must be a 40-character lowercase hex address")
        me = my_address()
        nonce = call("GET", f"{node}/account/{me}").json()["next_nonce"]
        print("Waiting for approval in the signer window...")
        r = call("POST", SIGNER + "/sign", json={
            "to": a.to, "amount": a.amount, "fee": a.fee, "nonce": nonce})
        if r.status_code != 200:
            die(r.json().get("error", "signer refused"))
        r = call("POST", node + "/tx", json=r.json())
        if r.status_code != 201:
            die(r.json().get("error", "node rejected the transaction"))
        print(f"sent {a.amount} to {a.to} (fee {a.fee}). Pending until a block is mined.")

    elif a.cmd == "mine":
        r = call("POST", f"{node}/mine/{my_address()}", headers=headers())
        if r.status_code != 200:
            die(r.json().get("error", "mining failed"))
        j = r.json()
        print(f"mined block {j['index']} (difficulty {j['bits']} bits) "
              f"with {j['txs'] - 1} transaction(s)")

if __name__ == "__main__":
    main()