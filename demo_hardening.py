import sys, requests
from auth import headers
from chaincore import Wallet

NODE = "http://127.0.0.1:5000"
PEER = "http://127.0.0.1:5001"

if len(sys.argv) > 1 and sys.argv[1] == "peers":
    print("saved peers:", requests.get(NODE + "/peers", headers=headers()).json())
    sys.exit()

addr = Wallet().address

def show(label, r):
    try:
        body = r.json()
    except ValueError:
        body = r.text[:60]
    print(f"{label:<28} {r.status_code} {body}")

print("--- access control")
show("mine, no token", requests.post(f"{NODE}/mine/{addr}"))
show("mine, wrong token", requests.post(f"{NODE}/mine/{addr}", headers={"X-Token": "guess"}))
show("mine, correct token", requests.post(f"{NODE}/mine/{addr}", headers=headers()))
show("mine, bad address", requests.post(f"{NODE}/mine/nothex", headers=headers()))

print("\n--- request size limit")
try:
    show("300 KB body to /tx", requests.post(
        NODE + "/tx", data=b"x" * 300_000,
        headers={"Content-Type": "application/json"}))
except requests.RequestException:
    print("300 KB body to /tx           connection closed by node (body refused)")

print("\n--- peer validation")
for bad in ["file:///etc/passwd", "ftp://127.0.0.1:5001",
            "http://user:pw@127.0.0.1:5001", "not a url"]:
    show(bad[:26], requests.post(NODE + "/peers", json={"url": bad}, headers=headers()))
show("valid peer", requests.post(NODE + "/peers", json={"url": PEER}, headers=headers()))

print("\n--- rate limit (130 quick requests)")
codes = [requests.get(f"{NODE}/account/{addr}").status_code for _ in range(130)]
print("200 responses:", codes.count(200), " 429 responses:", codes.count(429))

print("\nNow restart node 5000 and run:  python demo_hardening.py peers")
