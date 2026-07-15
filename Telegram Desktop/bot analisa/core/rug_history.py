import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

RUG_DB = Path(__file__).parent.parent / "data" / "rug_history.json"


def _load_db() -> Dict:
    if RUG_DB.exists():
        try:
            return json.loads(RUG_DB.read_text())
        except Exception:
            return {"events": [], "deployers": {}}
    return {"events": [], "deployers": {}}


def _save_db(db: Dict):
    RUG_DB.parent.mkdir(exist_ok=True, parents=True)
    RUG_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def add_rug_event(token_address: str, token_symbol: str, deployer: str,
                  signal_at_time: str = "", price_drop_pct: float = 0,
                  lp_removed_pct: float = 0, mcap_before: float = 0,
                  reason: str = "unknown") -> Dict:
    db = _load_db()
    now = datetime.now(timezone.utc).isoformat()

    event = {
        "token_address": token_address,
        "token_symbol": token_symbol,
        "deployer": deployer,
        "signal_at_time": signal_at_time,
        "price_drop_pct": round(price_drop_pct, 1),
        "lp_removed_pct": round(lp_removed_pct, 1),
        "mcap_before": mcap_before,
        "reason": reason,
        "detected_at": now,
    }
    db["events"].append(event)

    if deployer:
        dep_events = db["deployers"].get(deployer, {"events": [], "total_rugs": 0})
        dep_events["events"].append(token_address)
        dep_events["total_rugs"] = dep_events.get("total_rugs", 0) + 1
        dep_events["last_rug"] = now
        db["deployers"][deployer] = dep_events

    _save_db(db)
    return event


def check_deployer_rug_history(deployer: str) -> Dict:
    if not deployer:
        return {"has_rug_history": False, "total_rugs": 0, "events": []}

    db = _load_db()
    dep = db["deployers"].get(deployer)
    if not dep or dep.get("total_rugs", 0) == 0:
        return {"has_rug_history": False, "total_rugs": 0, "events": []}

    events = [e for e in db["events"] if e.get("deployer") == deployer]
    return {
        "has_rug_history": True,
        "total_rugs": dep["total_rugs"],
        "last_rug": dep.get("last_rug", ""),
        "rugged_tokens": dep.get("events", []),
        "events": events[-10:],
    }


def get_rug_stats(days: int = 30) -> Dict:
    db = _load_db()
    now = datetime.now(timezone.utc)

    total_rugs = len(db["events"])
    unique_deployers = len(db["deployers"])
    recent = 0
    for e in db["events"]:
        try:
            t = datetime.fromisoformat(e["detected_at"])
            if (now - t).days <= days:
                recent += 1
        except Exception:
            pass

    top_deployers = sorted(db["deployers"].items(),
                           key=lambda x: x[1].get("total_rugs", 0),
                           reverse=True)[:10]

    return {
        "total_rugs": total_rugs,
        "unique_deployers": unique_deployers,
        f"rugs_last_{days}d": recent,
        "top_deployers": [
            {"address": addr, "total_rugs": d.get("total_rugs", 0),
             "last_rug": d.get("last_rug", "")[:10]}
            for addr, d in top_deployers
        ],
    }


def get_rug_events(limit: int = 20) -> List[Dict]:
    db = _load_db()
    return list(reversed(db["events"]))[:limit]
