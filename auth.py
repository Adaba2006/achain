import os, secrets

TOKEN_FILE = "node_token.txt"

def get_token():
    env = os.environ.get("NODE_TOKEN")
    if env:
        return env
    if not os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "x") as f:
                f.write(secrets.token_hex(16))
        except FileExistsError:
            pass
    with open(TOKEN_FILE) as f:
        return f.read().strip()

def headers():
    return {"X-Token": get_token()}