import hashlib, json, time

def make_hash(block):
    text = json.dumps(block, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()

def new_block(index, data, prev_hash):
    return {
        "index": index,
        "time": time.time(),
        "data": data,
        "prev_hash": prev_hash,
    }

def is_valid(chain):
    for i in range(1, len(chain)):
        if chain[i]["prev_hash"] != make_hash(chain[i - 1]):
            return False
    return True

# build a chain
chain = [new_block(0, "genesis", "0")]
chain.append(new_block(1, "Alice pays Bob 5", make_hash(chain[0])))
chain.append(new_block(2, "Bob pays Carol 2", make_hash(chain[1])))

print("valid before tampering:", is_valid(chain))

# tamper with an old block
chain[1]["data"] = "Alice pays Bob 5000"

print("valid after tampering:", is_valid(chain))