"""End-to-end checks for the merkle_claim airdrop module (engine level)."""
import sys, os, types, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The real backend.crypto pulls in the third-party `cryptography` package for
# ECDSA keys; the claim engine only needs SHA-256, so stub it for this test.
_stub = types.ModuleType("cryptography")
_hp = types.ModuleType("cryptography.hazmat.primitives")
class _Curve:  # minimal stand-in for SECP256K1
    pass
_hp.hashes = types.SimpleNamespace()
_hp.serialization = types.SimpleNamespace()
sys.modules["cryptography"] = _stub
sys.modules["cryptography.hazmat"] = types.ModuleType("cryptography.hazmat")
sys.modules["cryptography.hazmat.primitives"] = _hp
sys.modules["cryptography.hazmat.primitives.hashes"] = _hp.hashes
sys.modules["cryptography.hazmat.primitives.serialization"] = _hp.serialization
_asym = types.ModuleType("cryptography.hazmat.primitives.asymmetric")
_asym.ec = types.SimpleNamespace(SECP256K1=_Curve)
sys.modules["cryptography.hazmat.primitives.asymmetric"] = _asym

from backend import crypto
from backend.contract import ContractEngine
from backend.merkle import MerkleTree
from backend.state import WorldState
from backend.templates import get_template

OWNER = "0x" + "a" * 40
A = "0x" + "1" * 40
B = "0x" + "2" * 40
C = "0x" + "3" * 40          # whitelisted
OUTSIDER = "0x" + "9" * 40   # not whitelisted
ADDR = "0xc_claim"

wls = sorted([A, B, C])
tree = MerkleTree([crypto.sha256(x) for x in wls])
ROOT = tree.root.hex()
proof_for = {a: [[s["dir"], s["hash"]] for s in tree.proof(i)]
             for i, a in enumerate(wls)}

engine = ContractEngine({})
ws = WorldState()
ws.set_balance(OWNER, 10000)
ws.set_balance(OUTSIDER, 5)

fails = []
def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        fails.append(name)

# 1. deploy with constructor args
tpl = get_template("merkle_claim")
r = engine.deploy(tpl["source"], OWNER, ADDR, ws,
                  constructor=[ROOT, 100, len(wls), 10], height=2)
check("deploy ok", r["ok"], r.get("error") or "")
check("deploy event", any(e["event"] == "ClaimCampaignCreated" for e in r["events"]))

# 2. fund the contract via deposit (value=300).  At chain level the call's
#    value is credited to the contract before invoke (see _execute_transaction).
ws.add_balance(OWNER, -300)
ws.add_balance(ADDR, 300)
r = engine.invoke(ADDR, "deposit", [], OWNER, 300, ws, height=3)
check("deposit ok", r["ok"], r.get("error") or "")
check("contract balance 300", ws.balance(ADDR) == 300)

# 3. valid claim by A
r = engine.invoke(ADDR, "claim", [proof_for[A]], A, 0, ws, height=4)
check("A claim ok", r["ok"], r.get("error") or "")
check("A received 100", ws.balance(A) == 100)
check("claim event emitted", any(e["event"] == "Claimed" for e in r["events"]))

# 4. double claim rejected (state revert -> balance unchanged)
r = engine.invoke(ADDR, "claim", [proof_for[A]], A, 0, ws, height=5)
check("A double claim rejected", not r["ok"] and "已领取" in (r["error"] or ""),
      r.get("error") or "")
check("A balance still 100", ws.balance(A) == 100)

# 5. outsider with no valid proof rejected
r = engine.invoke(ADDR, "claim", [proof_for[B]], OUTSIDER, 0, ws, height=5)
check("outsider with B proof rejected", not r["ok"] and "白名单" in (r["error"] or ""),
      r.get("error") or "")
check("outsider balance unchanged", ws.balance(OUTSIDER) == 5)

# 6. outsider with empty proof rejected
r = engine.invoke(ADDR, "claim", [], OUTSIDER, 0, ws, height=5)
check("outsider empty proof rejected", not r["ok"], r.get("error") or "")

# 7. tampered proof rejected
bad = [["R", "00" * 32] for _ in proof_for[B]]
r = engine.invoke(ADDR, "claim", [bad], B, 0, ws, height=5)
check("B tampered proof rejected", not r["ok"], r.get("error") or "")

# 8. B claims legitimately
r = engine.invoke(ADDR, "claim", [proof_for[B]], B, 0, ws, height=6)
check("B claim ok", r["ok"], r.get("error") or "")
check("B received 100", ws.balance(B) == 100)

# 9. info / progress queries
r = engine.simulate(ADDR, "info", [], OWNER, ws, height=6)
info = r["return"]
check("claimed_count=2", info["claimed_count"] == 2, str(info))
check("remaining_slots=1", info["remaining_slots"] == 1)
check("contract_balance=100", info["contract_balance"] == 100)
check("active at h6", info["active"] is True)
r = engine.simulate(ADDR, "has_claimed", [A], OWNER, ws, height=6)
check("has_claimed(A)=True", r["return"] is True)
r = engine.simulate(ADDR, "has_claimed", [C], OWNER, ws, height=6)
check("has_claimed(C)=False", r["return"] is False)

# 10. recover before deadline rejected for everyone
r = engine.invoke(ADDR, "recover_remaining", [], OWNER, 0, ws, height=10)
check("recover at end_height rejected", not r["ok"] and "截止" in (r["error"] or ""),
      r.get("error") or "")
r = engine.invoke(ADDR, "recover_remaining", [], A, 0, ws, height=11)
check("non-owner recover rejected", not r["ok"] and "项目方" in (r["error"] or ""),
      r.get("error") or "")

# 11. claim after deadline rejected
r = engine.invoke(ADDR, "claim", [proof_for[C]], C, 0, ws, height=11)
check("C claim after deadline rejected", not r["ok"] and "截止" in (r["error"] or ""),
      r.get("error") or "")
check("C got nothing", ws.balance(C) == 0)

# 12. owner recovers remaining after deadline
before = ws.balance(OWNER)
r = engine.invoke(ADDR, "recover_remaining", [], OWNER, 0, ws, height=11)
check("owner recover ok", r["ok"], r.get("error") or "")
check("owner got 100 remaining", ws.balance(OWNER) - before == 100,
      str(ws.balance(OWNER) - before))
check("contract drained", ws.balance(ADDR) == 0)
check("recover event", any(e["event"] == "Recovered" for e in r["events"]))

# 13. double recover rejected
r = engine.invoke(ADDR, "recover_remaining", [], OWNER, 0, ws, height=12)
check("double recover rejected", not r["ok"], r.get("error") or "")

# 14. claim after recovery rejected
r = engine.invoke(ADDR, "claim", [proof_for[C]], C, 0, ws, height=9)
check("claim after recovery rejected", not r["ok"], r.get("error") or "")

# 15. info final state
r = engine.simulate(ADDR, "info", [], OWNER, ws, height=12)
info = r["return"]
check("info recovered=True", info["recovered"] is True)
check("info active=False at h12", info["active"] is False)

# 16. bad constructor: past deadline rejected with state revert
BAD = "0xc_bad"
r = engine.deploy(tpl["source"], OWNER, BAD, ws,
                  constructor=[ROOT, 100, 3, 1], height=5)
check("deploy past deadline rejected", not r["ok"], r.get("error") or "")
check("failed deploy created no contract", BAD not in ws.contracts)

print()
if fails:
    print(f"{len(fails)} FAILURES:", fails)
    sys.exit(1)
print("ALL TESTS PASSED")
