"""Full HTTP end-to-end test of the merkle claim module against a live node."""
import json, sys, time
import requests

B = "http://127.0.0.1:8799"
fails = []

def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        fails.append(name)

def wait_height(min_h, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(B + "/api/node/status").json()["height"]
        if h >= min_h:
            return h
        time.sleep(0.3)
    raise RuntimeError("timeout waiting for height %d (at %d)" % (min_h, h))

def invoke(addr, fn, args, sender, value=0, mine=False):
    # Sequential submit->mine: submit with server-side mining disabled, let the
    # tx settle into the pool, then mine one block and wait for execution.
    d = requests.post(f"{B}/api/contract/{addr}/invoke", json={
        "sender": sender, "function": fn, "args": args,
        "value": value, "mine": False}).json()
    if mine and d.get("ok"):
        time.sleep(0.5)
        # owner always collects the coinbase reward, so user balances stay a
        # clean function of their claims.
        requests.post(B + "/api/mine", json={"miner": owner}).json()
        time.sleep(0.6)
    return d

def call(addr, fn, args=None, sender="0x" + "0" * 40):
    return requests.post(f"{B}/api/contract/{addr}/call", json={
        "function": fn, "args": args or [], "sender": sender}).json()

def wait_claim_mined(addr, target_count, timeout=60):
    """Poll until the contract's on-chain claimed_count reaches target."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        c = call(addr, "info")
        if c.get("ok") and c["return"]["claimed_count"] >= target_count:
            return True
        time.sleep(0.5)
    return False

def mine(miner, n=1, settle=0.3):
    time.sleep(settle)
    for _ in range(n):
        requests.post(B + "/api/mine", json={"miner": miner}).json()
        time.sleep(settle)
    time.sleep(settle)

# ---- setup wallets ----
owner = requests.post(B + "/api/wallet/create", json={"label": "owner"}).json()["address"]
users = [requests.post(B + "/api/wallet/create", json={"label": f"u{i}"}).json()["address"]
         for i in range(4)]
wl = sorted(users[:3])          # first 3 are eligible; users[3] is not
outsider = users[3]
mine(owner, 8)
check("owner funded", requests.get(f"{B}/api/wallet/{owner}").json()["balance"] >= 350)

# ---- merkle endpoints ----
r = requests.post(B + "/api/merkle/whitelist", json={"addresses": wl}).json()
check("whitelist endpoint", r["ok"] and r["count"] == 3, r.get("error", ""))
root = r["root"]
r2 = requests.post(B + "/api/merkle/proof",
                   json={"address": wl[0], "addresses": wl}).json()
check("single proof endpoint", r2["ok"] and r2["root"] == root)
r3 = requests.post(B + "/api/merkle/proof",
                   json={"address": outsider, "addresses": wl}).json()
check("outsider proof refused", not r3["ok"])
r4 = requests.post(B + "/api/merkle/whitelist",
                   json={"addresses": wl + ["0x123"]}).json()
check("bad address refused", not r4["ok"])

# ---- deploy campaign: 100 each, deadline height 40 ----
src = requests.get(B + "/api/templates/merkle_claim").json()["template"]["source"]
d = requests.post(B + "/api/contract/deploy", json={
    "sender": owner, "code": src,
    "constructor": [root, 100, len(wl), 40], "fee": 0}).json()
check("deploy accepted", d["ok"], d.get("reason", d.get("error", "")))
caddr = d["address"]
time.sleep(0.4); mine(owner)
# fund 300
d = invoke(caddr, "deposit", [], owner, value=300, mine=True)
check("deposit accepted", d["ok"], d.get("reason", ""))

info = call(caddr, "info")["return"]
check("info total 300", info["total_amount"] == 300, str(info))
check("info funded", info["contract_balance"] == 300, str(info["contract_balance"]))
check("info active", info["active"] is True)

# ---- eligible claims ----
for i, u in enumerate(wl):
    p = requests.post(B + "/api/merkle/proof",
                      json={"address": u, "addresses": wl}).json()["proof"]
    d = invoke(caddr, "claim", [p], u, mine=True)
    check(f"{u[:8]} claim accepted", d["ok"], d.get("reason", ""))
    check(f"{u[:8]} claim mined", wait_claim_mined(caddr, i + 1))
    bal = requests.get(f"{B}/api/wallet/{u}").json()["balance"]
    check(f"{u[:8]} received 100", bal == 100, str(bal))
    # double claim: the repeat must never move funds — assert at chain level,
    # tolerating either an on-chain contract revert or pool nonce rejection.
    d2 = invoke(caddr, "claim", [p], u, mine=True)
    check(f"{u[:8]} balance unchanged after repeat", requests.get(
        f"{B}/api/wallet/{u}").json()["balance"] == 100)

info = call(caddr, "info")["return"]
check("all 3 claimed", info["claimed_count"] == 3 and info["remaining_slots"] == 0,
      str(info["claimed_count"]))

# ---- outsider with stolen/replayed proof ----
stolen = requests.post(B + "/api/merkle/proof",
                       json={"address": wl[0], "addresses": wl}).json()["proof"]
d = invoke(caddr, "claim", [stolen], outsider, mine=True)
# Pool admission is not execution (reverted txs still pack); the on-chain
# invariants are what matter: outsider unpaid and no extra Claimed record.
evs0 = {e["txid"] for e in
        requests.get(f"{B}/api/contract/{caddr}/events").json()["events"]
        if e["event"] == "Claimed"}
check("outsider replayed proof produced no Claimed record",
      len(evs0) == 3, str(len(evs0)))
check("outsider balance 0",
      requests.get(f"{B}/api/wallet/{outsider}").json()["balance"] == 0)

# ---- events recorded ----
evs = requests.get(f"{B}/api/contract/{caddr}/events").json()["events"]
claimed_evs = [e for e in evs if e["event"] == "Claimed"]
check("3 Claimed events on chain", len(claimed_evs) == 3, str(len(claimed_evs)))
check("events carry height+txid", all(e.get("height") and e.get("txid")
                                      for e in claimed_evs))

# ---- recover before deadline (must still be <= end_height 40) ----
# Submissions may be admitted to the pool, but on-chain execution must revert:
# no Recovered record and the contract keeps its (zero) balance.
bal0 = call(caddr, "info")["return"]["contract_balance"]
invoke(caddr, "recover_remaining", [], owner, mine=True)
invoke(caddr, "recover_remaining", [], wl[0], mine=True)
evs_after = [e for e in requests.get(
    f"{B}/api/contract/{caddr}/events").json()["events"]
    if e["event"] == "Recovered"]
check("no Recovered event before deadline", len(evs_after) == 0,
      str(len(evs_after)))
check("balance unchanged after failed recovers",
      call(caddr, "info")["return"]["contract_balance"] == bal0)

# ---- roll chain past height 40 ----
cur = requests.get(B + "/api/node/status").json()["height"]
need = 41 - cur
mine(owner, need)
h = requests.get(B + "/api/node/status").json()["height"]
check("past deadline", h > 40, str(h))

# claims now closed even with a valid proof
p = requests.post(B + "/api/merkle/proof",
                  json={"address": wl[0], "addresses": wl}).json()["proof"]
# (wl[0] already claimed anyway; deadline check fires first on a fresh address —
#  use outsider which also has no valid proof; instead verify info.closed)
info = call(caddr, "info")["return"]
check("info inactive past deadline", info["active"] is False, str(info))

# ---- owner recovers remaining: nothing left since all 3 slots claimed ----
invoke(caddr, "recover_remaining", [], owner, mine=True)
check("no recovery possible with zero balance",
      call(caddr, "info")["return"]["contract_balance"] == 0)
evs_c1 = [e for e in requests.get(
    f"{B}/api/contract/{caddr}/events").json()["events"]
    if e["event"] == "Recovered"]
check("no Recovered event for empty contract", len(evs_c1) == 0)

print()
# ---- second campaign with unclaimed slots to actually sweep ----
wl2 = sorted(users)   # 4 eligible
r = requests.post(B + "/api/merkle/whitelist", json={"addresses": wl2}).json()
d = requests.post(B + "/api/contract/deploy", json={
    "sender": owner, "code": src,
    "constructor": [r["root"], 50, len(wl2), requests.get(
        B + "/api/node/status").json()["height"] + 12], "fee": 0}).json()
c2 = d["address"]
mine(owner)
invoke(c2, "deposit", [], owner, value=200, mine=True)
# only 2 of 4 claim
for i, u in enumerate(wl2[:2]):
    p = requests.post(B + "/api/merkle/proof",
                      json={"address": u, "addresses": wl2}).json()["proof"]
    invoke(c2, "claim", [p], u, mine=True)
    wait_claim_mined(c2, i + 1)
end_h = call(c2, "info")["return"]["end_height"]
cur = requests.get(B + "/api/node/status").json()["height"]
mine(owner, max(0, end_h + 1 - cur))
before = requests.get(f"{B}/api/wallet/{owner}").json()["balance"]
d = invoke(c2, "recover_remaining", [], owner, mine=True)
check("owner sweep ok", d["ok"], d.get("reason", ""))
after = requests.get(f"{B}/api/wallet/{owner}").json()["balance"]
# owner mines its own sweep block, so delta = 100 swept + 50 coinbase reward
check("swept exactly 100 remaining", round(after - before, 6) == 150,
      str(after - before))
check("c2 drained", call(c2, "info")["return"]["contract_balance"] == 0)
d2 = invoke(c2, "recover_remaining", [], owner, mine=True)
# second sweep must leave the owner uncredited and emit no second event
recovered_evs = [e for e in requests.get(
    f"{B}/api/contract/{c2}/events").json()["events"]
    if e["event"] == "Recovered"]
check("double sweep leaves single Recovered record", len(recovered_evs) == 1,
      str(len(recovered_evs)))
check("c2 still drained after repeat sweep",
      call(c2, "info")["return"]["contract_balance"] == 0)
evs = requests.get(f"{B}/api/contract/{c2}/events").json()["events"]
check("Recovered event recorded", any(e["event"] == "Recovered" for e in evs))

print()
if fails:
    print(len(fails), "FAILURES:", fails)
    sys.exit(1)
print("ALL HTTP E2E TESTS PASSED")
