import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config import HELIUS_API_KEY
from core.helius import HeliusClient

SMART_FILE = Path(__file__).parent.parent / "data" / "smart_money.json"

DEFAULT_LEARNED = []


def load_smart_money() -> Dict:
    if SMART_FILE.exists():
        try:
            data = json.loads(SMART_FILE.read_text())
            data.setdefault("wallets", [])
            data.setdefault("early_buyers", {})
            return data
        except Exception:
            pass
    return {"wallets": [], "early_buyers": {}}


def save_smart_money(store: Dict):
    SMART_FILE.parent.mkdir(exist_ok=True, parents=True)
    SMART_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=False, default=str))


def load_smart_wallets() -> List[Dict]:
    return load_smart_money().get("wallets", [])


def add_smart_wallet(address: str, name: str = "") -> Dict:
    store = load_smart_money()
    for w in store["wallets"]:
        if w["address"] == address:
            return w
    rec = {
        "address": address,
        "name": name or f"Smart {address[:8]}",
        "realized_pnl_pct": 0,
        "hit_count": 0,
        "tracked_since": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
    }
    store["wallets"].append(rec)
    save_smart_money(store)
    return rec


def remove_smart_wallet(address: str) -> bool:
    store = load_smart_money()
    new = [w for w in store["wallets"] if w["address"] != address]
    if len(new) < len(store["wallets"]):
        store["wallets"] = new
        save_smart_money(store)
        return True
    return False


def record_early_buyers(token_address: str, launch_at: Optional[str], buyer_addresses: List[str]):
    if not token_address or not buyer_addresses:
        return
    store = load_smart_money()
    existing = store["early_buyers"].get(token_address)
    if existing:
        return
    store["early_buyers"][token_address] = {
        "buyers": list(dict.fromkeys(buyer_addresses))[:40],
        "launch_at": launch_at or datetime.now(timezone.utc).isoformat(),
        "seen_at": datetime.now(timezone.utc).isoformat(),
        "learned": False,
    }
    save_smart_money(store)


def learn_from_feedback() -> bool:
    from core.feedback_tracker import load_feedback

    fb = load_feedback()
    if not fb.get("signals"):
        return False

    store = load_smart_money()
    learned = {w["address"]: w for w in store["wallets"] if w.get("source") == "learned"}
    changed = False
    now = datetime.now(timezone.utc).isoformat()

    for sig in fb["signals"]:
        if sig.get("status") != "closed":
            continue
        tok = sig.get("token", "")
        eb = store["early_buyers"].get(tok)
        if not eb or eb.get("learned"):
            continue

        outcome = sig.get("outcome")
        pnl = sig.get("final_pnl") or 0
        for addr in eb["buyers"]:
            rec = learned.get(addr)
            if outcome == "win":
                if rec:
                    rec["hit_count"] += 1
                    rec["realized_pnl_pct"] = round((rec["realized_pnl_pct"] + pnl) / 2, 1)
                else:
                    rec = {
                        "address": addr,
                        "name": f"Smart {addr[:8]}",
                        "realized_pnl_pct": round(pnl, 1),
                        "hit_count": 1,
                        "tracked_since": now,
                        "source": "learned",
                    }
                    learned[addr] = rec
                    store["wallets"].append(rec)
                changed = True
            elif outcome == "loss":
                if rec and rec["hit_count"] > 0:
                    rec["hit_count"] -= 1
                    if rec["hit_count"] <= 0:
                        store["wallets"] = [w for w in store["wallets"] if w["address"] != addr]
                        learned.pop(addr, None)
                    changed = True
        eb["learned"] = True

    if changed:
        save_smart_money(store)
    return changed


async def analyze_smart_money(token_address: str) -> Dict:
    if not token_address:
        return _empty_result()

    learn_from_feedback()

    store = load_smart_money()
    known = store.get("wallets", [])

    client = HeliusClient(HELIUS_API_KEY)
    smart_holders = []
    retention = None
    insider_selling = False

    try:
        for w in known:
            try:
                bal = await client.get_token_balance(w["address"], token_address)
            except Exception:
                bal = None
            if bal and float(bal.get("ui_amount", 0) or 0) > 0:
                smart_holders.append({
                    "wallet": w["address"],
                    "name": w.get("name", w["address"][:8]),
                    "amount": bal.get("ui_amount", 0),
                    "hit_count": w.get("hit_count", 0),
                    "source": w.get("source", "manual"),
                })

        eb = store.get("early_buyers", {}).get(token_address)
        if eb and eb.get("buyers"):
            buyers = set(eb["buyers"])
            try:
                holders = await client.get_token_largest_holders(token_address, limit=30)
            except Exception:
                holders = []
            current = {h.get("address", "") for h in holders}
            if buyers and current:
                retained = buyers & current
                sold = buyers - current
                retention = round(len(retained) / len(buyers) * 100, 1)
                if len(sold) >= max(2, int(len(buyers) * 0.4)):
                    insider_selling = True
    finally:
        await client.close()

    smart_count = len(smart_holders)
    score_adj = 0
    if smart_count > 0:
        score_adj += min(smart_count * 5, 15)
    if insider_selling:
        score_adj -= 15
    if retention is not None:
        if retention >= 70:
            score_adj += 5
        elif retention < 30:
            score_adj -= 5

    if insider_selling:
        risk = "high"
    elif smart_count == 0 and retention is not None and retention < 50:
        risk = "medium"
    else:
        risk = "low"

    signal = "AVOID" if insider_selling else ("BUY" if smart_count > 0 else "WATCH")

    return {
        "found": True,
        "smart_holders": smart_holders,
        "smart_holder_count": smart_count,
        "insider_selling": insider_selling,
        "early_buyer_retention_pct": retention,
        "score_adjustment": score_adj,
        "risk": risk,
        "signal": signal,
    }


def _empty_result() -> Dict:
    return {
        "found": False,
        "smart_holders": [],
        "smart_holder_count": 0,
        "insider_selling": False,
        "early_buyer_retention_pct": None,
        "score_adjustment": 0,
        "risk": "unknown",
        "signal": "WATCH",
    }
