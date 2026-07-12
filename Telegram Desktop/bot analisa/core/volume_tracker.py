import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


VOLUME_FILE = Path(__file__).parent.parent / "data" / "volume_history.json"
SPIKE_THRESHOLD = 200
SPIKE_WINDOW_MINUTES = 5


def load_history() -> Dict[str, List[Dict]]:
    if VOLUME_FILE.exists():
        try:
            return json.loads(VOLUME_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_history(history: Dict[str, List[Dict]]):
    VOLUME_FILE.parent.mkdir(exist_ok=True, parents=True)

    for addr in list(history.keys()):
        if len(history[addr]) > 50:
            history[addr] = history[addr][-30:]

    VOLUME_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def record_volume(token_address: str, symbol: str, volume_24h: float, mcap: float, liq: float):
    history = load_history()
    key = token_address

    if key not in history:
        history[key] = []

    history[key].append({
        "time": datetime.now(timezone.utc).isoformat(),
        "volume": volume_24h,
        "mcap": mcap,
        "liq": liq,
        "symbol": symbol,
    })

    save_history(history)


def detect_spikes() -> List[Dict]:
    history = load_history()
    spikes = []

    for addr, snapshots in history.items():
        if len(snapshots) < 2:
            continue

        latest = snapshots[-1]
        previous = snapshots[-2]

        latest_time = datetime.fromisoformat(latest["time"])
        prev_time = datetime.fromisoformat(previous["time"])
        time_diff = (latest_time - prev_time).total_seconds() / 60

        if time_diff > SPIKE_WINDOW_MINUTES * 2:
            continue

        latest_vol = latest.get("volume", 0)
        prev_vol = previous.get("volume", 0)

        if prev_vol == 0 or latest_vol == 0:
            continue

        change_pct = ((latest_vol - prev_vol) / prev_vol) * 100

        if change_pct >= SPIKE_THRESHOLD:
            spikes.append({
                "token_address": addr,
                "symbol": latest.get("symbol", "???"),
                "volume_now": latest_vol,
                "volume_before": prev_vol,
                "spike_pct": round(change_pct, 1),
                "mcap": latest.get("mcap", 0),
                "liq": latest.get("liq", 0),
                "time_diff_minutes": round(time_diff, 1),
            })

    spikes.sort(key=lambda x: x["spike_pct"], reverse=True)
    return spikes
