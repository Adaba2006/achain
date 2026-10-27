import hashlib, json, time

DIFFICULTY = 6   # required leading zeros in the hash

def make_hash(block):
    text = json.dumps(block, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()

def mine_block(index, data, prev_hash):
    block = {
        "index": index,
        "time": time.time(),
        "data": data,
        "prev_hash": prev_hash,
        "nonce": 0,
    }
    while not make_hash(block).startswith("0" * DIFFICULTY):
        block["nonce"] += 1
    return block

def is_valid(chain):
    for i, block in enumerate(chain):
        if not make_hash(block).startswith("0" * DIFFICULTY):
            return False                      # work not done
        if i > 0 and block["prev_hash"] != make_hash(chain[i - 1]):
            return False                      # broken link
    return True

# build the chain and time the mining
start = time.time()
chain = [mine_block(0, "genesis", "0")]
chain.append(mine_block(1, "Alice pays Bob 5", make_hash(chain[0])))
chain.append(mine_block(2, "Bob pays Carol 2", make_hash(chain[1])))
print("mining took %.2f seconds" % (time.time() - start))

for b in chain:
    print("block", b["index"], "nonce", b["nonce"], "hash", make_hash(b)[:16], "...")

print("valid before tampering:", is_valid(chain))

# test 1: tamper with the LAST block
chain[2]["data"] = "Bob pays Carol 2000"
print("valid after editing last block:", is_valid(chain))
chain[2]["data"] = "Bob pays Carol 2"        # undo

# test 2: tamper with an OLD block
chain[1]["data"] = "Alice pays Bob 5000"
print("valid after editing old block:", is_valid(chain))