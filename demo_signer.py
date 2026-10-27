import requests
from auth import headers
from chaincore import Wallet

SIGNER, NODE = "http://127.0.0.1:6000", "http://127.0.0.1:5000"

me = requests.get(SIGNER + "/pubkey").json()["address"]
recipient = Wallet().address        # throwaway wallet: only its address is used

def account(addr):
    return requests.get(f"{NODE}/account/{addr}").json()

def ask(amount):
    return requests.post(SIGNER + "/sign", json={
        "to": recipient, "amount": amount, "fee": 1,
        "nonce": account(me)["next_nonce"]})

print("signer balance before:", account(me)["balance"])

print("\n1) normal request: approve it in the signer window")
r = ask(10)
if r.status_code == 200:
    print("node accepted:", requests.post(NODE + "/tx", json=r.json()).status_code)
    requests.post(f"{NODE}/mine/{me}", headers=headers())
else:
    print("signer refused:", r.json())

print("\n2) over the signer's limit")
r = ask(600)
print(r.status_code, r.json())

print("\n3) a request you deny: type n in the signer window")
r = ask(5)
print(r.status_code, r.json())

print("\nrecipient balance:", account(recipient)["balance"])
print("signer balance after:", account(me)["balance"])
