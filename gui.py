import json, queue, re, sys, threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, scrolledtext

import requests

from auth import headers
from chaincore import make_hash

NODE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
SIGNER = "http://127.0.0.1:6000"
ADDRESS_RE = re.compile(r"[0-9a-f]{40}")
SHOW_BLOCKS = 15
REFRESH_MS = 10000


class App:
    def __init__(self, root):
        self.root = root
        root.title("Chain Wallet and Explorer")
        root.geometry("820x600")
        ttk.Style().theme_use("clam")
        self.q = queue.Queue()
        self.address = None
        self.blocks = []
        self.refreshing = False
        self.build()
        self.poll()
        self.refresh()
        root.after(REFRESH_MS, self.auto_refresh)

    # ---------- layout ----------
    def build(self):
        self.status = tk.StringVar(value="Starting...")
        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w", padding=4).pack(fill="x", side="bottom")

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        self.addr_var = tk.StringVar(value="(signer not running)")
        self.bal_var = tk.StringVar(value="-")
        self.info_var = tk.StringVar()
        ttk.Label(top, text="Address").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.addr_var, state="readonly",
                  width=50).grid(row=0, column=1, padx=6)
        ttk.Button(top, text="Copy", command=self.copy_address).grid(row=0, column=2)
        ttk.Label(top, text="Balance").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Label(top, textvariable=self.bal_var,
                  font=("Segoe UI", 18, "bold")).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(top, textvariable=self.info_var).grid(
            row=2, column=0, columnspan=3, sticky="w")
        bar = ttk.Frame(top)
        bar.grid(row=3, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Mine a block", command=self.mine).pack(side="left", padx=8)

        box = ttk.LabelFrame(self.root, text="Send coins", padding=10)
        box.pack(fill="x", padx=10)
        self.to_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.fee_var = tk.StringVar(value="1")
        ttk.Label(box, text="To").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.to_var, width=50).grid(
            row=0, column=1, columnspan=5, padx=6, sticky="w")
        ttk.Label(box, text="Amount").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(box, textvariable=self.amount_var, width=10).grid(
            row=1, column=1, padx=6, sticky="w")
        ttk.Label(box, text="Fee").grid(row=1, column=2, sticky="e")
        ttk.Entry(box, textvariable=self.fee_var, width=6).grid(row=1, column=3, padx=6)
        ttk.Button(box, text="Send", command=self.send).grid(row=1, column=4, padx=6)

        frame = ttk.LabelFrame(self.root, text="Latest blocks (double-click for details)",
                               padding=10)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        cols = ("index", "bits", "txs", "hash", "time")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (60, 60, 60, 280, 120)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.show_block)

    # ---------- background work ----------
    def bg(self, work, done):
        def run():
            try:
                self.q.put((done, work(), None))
            except Exception as e:
                self.q.put((done, None, e))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                done, result, err = self.q.get_nowait()
                done(result, err)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll)

    # ---------- refresh ----------
    def fetch_state(self):
        r = requests.get(NODE + "/chain", timeout=10)
        if r.status_code != 200:
            raise RuntimeError(r.json().get("error", f"node returned {r.status_code}"))
        chain = r.json()
        state = {"blocks": chain[-SHOW_BLOCKS:], "height": len(chain) - 1,
                 "address": None, "balance": None}
        try:
            addr = requests.get(SIGNER + "/pubkey", timeout=3).json()["address"]
            acct = requests.get(f"{NODE}/account/{addr}", timeout=10).json()
            state["address"], state["balance"] = addr, acct["balance"]
        except (requests.RequestException, KeyError, ValueError):
            pass                              # signer not running: show chain only
        return state

    def on_state(self, state, err):
        self.refreshing = False
        if err:
            self.status.set(f"Cannot read from node: {err}")
            return
        self.blocks = state["blocks"]
        self.address = state["address"]
        self.addr_var.set(self.address or "(signer not running)")
        self.bal_var.set(str(state["balance"]) if self.address else "-")
        bits = self.blocks[-1]["bits"] if self.blocks else "-"
        self.info_var.set(f"Chain height: {state['height']}    Current difficulty: {bits} bits")
        self.tree.delete(*self.tree.get_children())
        for b in reversed(self.blocks):
            when = datetime.fromtimestamp(b["time"]).strftime("%H:%M:%S") if b["time"] else "genesis"
            self.tree.insert("", "end", iid=str(b["index"]),
                             values=(b["index"], b["bits"], len(b["txs"]),
                                     make_hash(b)[:24], when))
        self.status.set("Updated")

    def refresh(self):
        if self.refreshing:
            return
        self.refreshing = True
        self.bg(self.fetch_state, self.on_state)

    def auto_refresh(self):
        self.refresh()
        self.root.after(REFRESH_MS, self.auto_refresh)

    # ---------- actions ----------
    def copy_address(self):
        if self.address:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.address)
            self.status.set("Address copied")

    def mine(self):
        if not self.address:
            messagebox.showwarning("Mine", "Start signer.py first, so the reward has an address.")
            return
        addr = self.address
        self.status.set("Mining...")

        def work():
            r = requests.post(f"{NODE}/mine/{addr}", headers=headers(), timeout=300)
            if r.status_code != 200:
                raise RuntimeError(r.json().get("error", "mining failed"))
            return r.json()

        def done(res, err):
            if err:
                self.status.set(f"Mining failed: {err}")
            else:
                self.status.set(f"Mined block {res['index']} ({res['bits']} bits, "
                                f"{res['txs'] - 1} transaction(s))")
            self.refresh()
        self.bg(work, done)

    def send(self):
        to = self.to_var.get().strip()
        try:
            amount, fee = int(self.amount_var.get()), int(self.fee_var.get())
        except ValueError:
            messagebox.showerror("Send", "Amount and fee must be whole numbers.")
            return
        if not ADDRESS_RE.fullmatch(to):
            messagebox.showerror("Send", "The recipient must be a 40-character lowercase hex address.")
            return
        if amount <= 0 or fee < 1:
            messagebox.showerror("Send", "Amount must be above 0 and the fee at least 1.")
            return
        if not self.address:
            messagebox.showwarning("Send", "Start signer.py first.")
            return
        addr = self.address
        self.status.set("Waiting for approval in the signer window...")

        def work():
            nonce = requests.get(f"{NODE}/account/{addr}", timeout=10).json()["next_nonce"]
            r = requests.post(SIGNER + "/sign", timeout=300, json={
                "to": to, "amount": amount, "fee": fee, "nonce": nonce})
            if r.status_code != 200:
                raise RuntimeError(r.json().get("error", "signer refused"))
            r = requests.post(NODE + "/tx", json=r.json(), timeout=10)
            if r.status_code != 201:
                raise RuntimeError(r.json().get("error", "node rejected the transaction"))

        def done(res, err):
            if err:
                self.status.set(f"Send failed: {err}")
            else:
                self.status.set(f"Sent {amount} (fee {fee}). Pending until a block is mined.")
                self.to_var.set("")
                self.amount_var.set("")
            self.refresh()
        self.bg(work, done)

    def show_block(self, _event):
        sel = self.tree.focus()
        block = next((b for b in self.blocks if str(b["index"]) == sel), None)
        if not block:
            return
        win = tk.Toplevel(self.root)
        win.title(f"Block {sel}")
        box = scrolledtext.ScrolledText(win, width=90, height=28)
        box.insert("1.0", f"hash: {make_hash(block)}\n\n" + json.dumps(block, indent=2))
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()