import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("memecoin-bot")

ALERTS_FILE = Path(__file__).parent.parent / "data" / "price_alerts.json"


def _load_alerts() -> List[Dict]:
    try:
        if ALERTS_FILE.exists():
            return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_alerts(alerts: List[Dict]):
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2, ensure_ascii=False), encoding="utf-8")


def add_price_alert(chat_id: str, token_address: str, symbol: str, entry_price: float, pct: float) -> Dict:
    alerts = _load_alerts()
    for a in alerts:
        if a["chat_id"] == chat_id and a["token_address"] == token_address and a["status"] == "active":
            if pct < 0:
                a["alert_down_pct"] = pct
            else:
                a["alert_up_pct"] = pct
            a["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_alerts(alerts)
            return a

    alert = {
        "chat_id": chat_id,
        "token_address": token_address,
        "symbol": symbol,
        "entry_price": entry_price,
        "alert_down_pct": pct if pct < 0 else 0,
        "alert_up_pct": pct if pct > 0 else 0,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    alerts.append(alert)
    _save_alerts(alerts)
    return alert


def remove_price_alert(chat_id: str, token_address: str) -> bool:
    alerts = _load_alerts()
    before = len(alerts)
    alerts = [a for a in alerts if not (a["chat_id"] == chat_id and a["token_address"] == token_address)]
    if len(alerts) < before:
        _save_alerts(alerts)
        return True
    return False


def get_alerts_for_chat(chat_id: str) -> List[Dict]:
    return [a for a in _load_alerts() if a["chat_id"] == chat_id and a["status"] == "active"]


def check_price_alerts(current_prices: Dict[str, float]) -> List[Dict]:
    alerts = _load_alerts()
    triggered = []
    remaining = []

    for alert in alerts:
        if alert["status"] != "active":
            remaining.append(alert)
            continue

        addr = alert["token_address"]
        current = current_prices.get(addr, 0)
        if current <= 0:
            remaining.append(alert)
            continue

        entry = alert.get("entry_price", 0)
        if entry <= 0:
            remaining.append(alert)
            continue

        change_pct = ((current - entry) / entry) * 100
        alert_down = alert.get("alert_down_pct", 0)
        alert_up = alert.get("alert_up_pct", 0)

        fired = False
        if alert_down < 0 and change_pct <= alert_down:
            triggered.append({**alert, "change_pct": round(change_pct, 2), "alert_type": "drop"})
            fired = True
        elif alert_up > 0 and change_pct >= alert_up:
            triggered.append({**alert, "change_pct": round(change_pct, 2), "alert_type": "rise"})
            fired = True

        if fired:
            alert["status"] = "triggered"
            alert["triggered_at"] = datetime.now(timezone.utc).isoformat()
            alert["trigger_price"] = current
            alert["change_pct"] = round(change_pct, 2)
        remaining.append(alert)

    _save_alerts(remaining)
    return triggered
