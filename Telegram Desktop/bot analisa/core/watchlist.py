import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


WATCHLIST_FILE = Path(__file__).parent.parent / "data" / "watchlist.json"


def load_watchlist() -> List[Dict]:
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text())
        except Exception:
            return []
    return []


def save_watchlist(items: List[Dict]):
    WATCHLIST_FILE.parent.mkdir(exist_ok=True, parents=True)
    WATCHLIST_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False))


def add_to_watchlist(address: str, symbol: str, name: str, mcap: float = 0, liq: float = 0, url: str = "") -> Dict:
    items = load_watchlist()

    for item in items:
        if item.get("address") == address:
            item["updated_at"] = datetime.now().isoformat()
            item["symbol"] = symbol
            item["name"] = name
            if mcap:
                item["mcap_added"] = mcap
            if liq:
                item["liq_added"] = liq
            if url:
                item["url"] = url
            save_watchlist(items)
            return item

    item = {
        "address": address,
        "symbol": symbol,
        "name": name,
        "mcap_added": mcap,
        "liq_added": liq,
        "url": url,
        "added_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "alerts": {
            "price_drop_pct": -50,
            "price_rise_pct": 100,
        },
        "snapshots": [],
    }
    items.append(item)
    save_watchlist(items)
    return item


def remove_from_watchlist(address: str) -> bool:
    items = load_watchlist()
    new_items = [i for i in items if i.get("address") != address]
    if len(new_items) < len(items):
        save_watchlist(new_items)
        return True
    return False


def get_watchlist_item(address: str) -> Optional[Dict]:
    items = load_watchlist()
    for item in items:
        if item.get("address") == address:
            return item
    return None


def add_price_snapshot(address: str, price: float, mcap: float, volume: float):
    items = load_watchlist()
    for item in items:
        if item.get("address") == address:
            snapshots = item.get("snapshots", [])
            snapshots.append({
                "time": datetime.now().isoformat(),
                "price": price,
                "mcap": mcap,
                "volume": volume,
            })
            if len(snapshots) > 100:
                snapshots = snapshots[-50:]
            item["snapshots"] = snapshots
            item["current_price"] = price
            item["current_mcap"] = mcap
            item["updated_at"] = datetime.now().isoformat()
            save_watchlist(items)
            return item
    return None


def check_watchlist_alerts() -> List[Dict]:
    items = load_watchlist()
    alerts = []

    for item in items:
        current = item.get("current_price", 0)
        snapshots = item.get("snapshots", [])
        threshold_down = item.get("alerts", {}).get("price_drop_pct", -50)
        threshold_up = item.get("alerts", {}).get("price_rise_pct", 100)

        if not snapshots or current == 0:
            continue

        oldest = snapshots[0].get("price", 0)
        if oldest == 0:
            continue

        change_pct = ((current - oldest) / oldest) * 100

        if change_pct <= threshold_down:
            alerts.append({**item, "alert_type": "price_drop", "change_pct": round(change_pct, 2)})
        elif change_pct >= threshold_up:
            alerts.append({**item, "alert_type": "price_rise", "change_pct": round(change_pct, 2)})

    return alerts
