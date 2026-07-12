import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone


MIGRATION_FILE = Path(__file__).parent.parent / "data" / "migration_history.json"


def load_migration_history() -> Dict[str, str]:
    if MIGRATION_FILE.exists():
        try:
            return json.loads(MIGRATION_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_migration_history(history: Dict[str, str]):
    MIGRATION_FILE.parent.mkdir(exist_ok=True, parents=True)
    MIGRATION_FILE.write_text(json.dumps(history, indent=2))


def check_migration(token_address: str, current_market_type: str) -> Optional[Dict]:
    history = load_migration_history()

    prev_type = history.get(token_address)
    prev_type_str = str(prev_type) if prev_type else ""

    if prev_type_str and "pump" in prev_type_str.lower() and "raydium" in str(current_market_type).lower():
        history[token_address] = current_market_type
        save_migration_history(history)
        return {
            "migrated": True,
            "from_market": prev_type_str,
            "to_market": current_market_type,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "signal": "PUMP_TO_RAYDIUM",
        }

    if str(current_market_type):
        history[token_address] = str(current_market_type)
        save_migration_history(history)

    return None


def detect_migrations_from_scan(tokens: List[Dict]) -> List[Dict]:
    migrations = []

    for token in tokens:
        addr = token.get("token_address", "")
        market_type = token.get("score", {}).get("details", {}).get("safety", {}).get("checks", {}).get("market_type", "")

        if not addr or not market_type:
            continue

        result = check_migration(addr, market_type)
        if result:
            migrations.append({
                **result,
                "token_address": addr,
                "symbol": token.get("symbol", "???"),
                "name": token.get("name", "?"),
                "score": token.get("score", {}).get("total_score", 0),
            })

    return migrations
