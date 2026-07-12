import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

TRADE_CONFIG_FILE = Path(__file__).parent.parent / "data" / "trade_config.json"
COOLDOWN_FILE = Path(__file__).parent.parent / "data" / "trade_cooldowns.json"


def load_trade_config(chat_id: str) -> Dict:
    if TRADE_CONFIG_FILE.exists():
        try:
            configs = json.loads(TRADE_CONFIG_FILE.read_text())
            return configs.get(chat_id, _default_config())
        except Exception:
            return _default_config()
    return _default_config()


def save_trade_config(chat_id: str, config: Dict):
    TRADE_CONFIG_FILE.parent.mkdir(exist_ok=True, parents=True)
    configs = {}
    if TRADE_CONFIG_FILE.exists():
        try:
            configs = json.loads(TRADE_CONFIG_FILE.read_text())
        except Exception:
            pass
    configs[chat_id] = config
    TRADE_CONFIG_FILE.write_text(json.dumps(configs, indent=2, ensure_ascii=False))


def _default_config() -> Dict:
    return {
        "partial_sell_enabled": True,
        "partial_sell_levels": [
            {"pct": 50, "sell_portion": 0.25},
            {"pct": 100, "sell_portion": 0.25},
            {"pct": 200, "sell_portion": 0.50},
        ],
        "trailing_stop_enabled": True,
        "trailing_stop_start": 50,
        "trailing_stop_distance": 20,
        "dynamic_buy_enabled": True,
        "dynamic_buy_amounts": {
            "10": 0.3,
            "9": 0.25,
            "8": 0.2,
            "7": 0.1,
            "6": 0.05,
        },
        "entry_timing_enabled": True,
        "entry_timing_delay": 120,
        "entry_timing_min_change": -10,
        "cooldown_enabled": True,
        "cooldown_hours": 6,
    }


def load_cooldowns() -> Dict[str, float]:
    if COOLDOWN_FILE.exists():
        try:
            return json.loads(COOLDOWN_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_cooldowns(cooldowns: Dict[str, float]):
    COOLDOWN_FILE.parent.mkdir(exist_ok=True, parents=True)
    COOLDOWN_FILE.write_text(json.dumps(cooldowns, indent=2))


def is_token_cooled_down(token_address: str, chat_id: str, cooldown_hours: int = 6) -> bool:
    cooldowns = load_cooldowns()
    key = f"{chat_id}_{token_address}"
    last_trade = cooldowns.get(key, 0)
    if last_trade == 0:
        return True
    elapsed = datetime.now(timezone.utc).timestamp() - last_trade
    return elapsed > cooldown_hours * 3600


def set_token_cooldown(token_address: str, chat_id: str):
    cooldowns = load_cooldowns()
    key = f"{chat_id}_{token_address}"
    cooldowns[key] = datetime.now(timezone.utc).timestamp()
    save_cooldowns(cooldowns)


def get_dynamic_buy_amount(confidence: int, default_amount: float = 0.1) -> float:
    config = _default_config()
    amounts = config.get("dynamic_buy_amounts", {})
    return amounts.get(str(confidence), default_amount)


def get_partial_sell_amounts() -> List[Dict]:
    config = _default_config()
    return config.get("partial_sell_levels", [])


def should_partial_sell(pnl_pct: float, level_pct: float, already_sold: float) -> float:
    if pnl_pct >= level_pct and already_sold < 1.0:
        return level_pct
    return 0


def get_trailing_stop(entry_price: float, highest_price: float, start_pct: int = 50, distance_pct: int = 20) -> Optional[float]:
    highest_pnl = ((highest_price - entry_price) / entry_price) * 100
    if highest_pnl < start_pct:
        return None
    stop_price = highest_price * (1 - distance_pct / 100)
    return stop_price
