import getpass, os, requests
from auth import headers
from chaincore import Wallet

A, B = "http://127.0.0.1:5000", "http://127.0.0.1:5001"
pw = getpass.getpass("Wallet password (same as before): ")

def get_wallet(path):
    if os.path.exists(path):
        return Wallet.load(path, pw)
    w = Wallet()
    w.save(path, pw)
    return w

def balance(url, w):
    return requests.get(f"{url}/account/{w.address}").json()["balance"]

def next_nonce(url, w):
    return requests.get(f"{url}/account/{w.address}").json()["next_nonce"]

alice, bob, miner = get_wallet("alice.pem"), get_wallet("bob.pem"), get_wallet("miner.pem")

requests.post(A + "/peers", json={"url": B}, headers=headers())
requests.post(B + "/peers", json={"url": A}, headers=headers())

# ---- difficulty adjustment ----
print("Mining 20 blocks on node A...")
for _ in range(20):
    requests.post(f"{A}/mine/{alice.address}", headers=headers())

chain = requests.get(A + "/chain").json()
print("block  bits  seconds since previous")
for blk, prev in zip(chain[1:], chain):
    gap = blk["time"] - prev["time"] if prev["index"] > 0 else 0.0
    print(f"{blk['index']:>5}  {blk['bits']:>4}  {gap:>8.2f}")

# ---- fees ----
print("\nFee test")
tx = alice.send(bob.address, 30, next_nonce(A, alice), fee=2)
print("tx with fee 2 accepted:", requests.post(A + "/tx", json=tx).status_code)
requests.post(f"{A}/mine/{miner.address}", headers=headers())
print("miner balance (50 reward + 2 fee):", balance(A, miner))
print("alice:", balance(A, alice), " bob:", balance(A, bob))

r = requests.post(A + "/tx", json=alice.send(bob.address, 5, next_nonce(A, alice), fee=0))
print("zero-fee tx:", r.status_code, r.json())

forged = dict(tx)
forged["fee"] = 3
r = requests.post(A + "/tx", json=forged)
print("forged fee:", r.status_code, r.json())

# ---- sync ----
print("\nSync")
print("B length before:", len(requests.get(B + "/chain").json()))
print("B sync:", requests.post(B + "/sync", headers=headers()).json())
print("miner on B:", balance(B, miner))
