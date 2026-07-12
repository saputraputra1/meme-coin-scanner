import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("memecoin-bot")

POSITIONS_FILE = Path(__file__).parent.parent / "data" / "positions.json"
TRADE_HISTORY_FILE = Path(__file__).parent.parent / "data" / "trade_history.json"


def load_positions() -> List[Dict]:
    if POSITIONS_FILE.exists():
        try:
            return json.loads(POSITIONS_FILE.read_text())
        except Exception:
            return []
    return []


def save_positions(positions: List[Dict]):
    POSITIONS_FILE.parent.mkdir(exist_ok=True, parents=True)
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2, ensure_ascii=False, default=str))


def load_trade_history() -> List[Dict]:
    if TRADE_HISTORY_FILE.exists():
        try:
            return json.loads(TRADE_HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def save_trade_history(history: List[Dict]):
    TRADE_HISTORY_FILE.parent.mkdir(exist_ok=True, parents=True)
    TRADE_HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False, default=str))


def add_position(chat_id: str, token_address: str, symbol: str, entry_price: float,
                 amount_sol: float, amount_tokens: float, tx_hash: str = "") -> Dict:
    positions = load_positions()

    position = {
        "id": f"{chat_id}_{token_address}",
        "chat_id": chat_id,
        "token_address": token_address,
        "symbol": symbol,
        "entry_price": entry_price,
        "current_price": entry_price,
        "highest_price": entry_price,
        "amount_sol": amount_sol,
        "amount_tokens": amount_tokens,
        "pnl_pct": 0,
        "pnl_sol": 0,
        "status": "open",
        "partial_sold": 0,
        "partial_sold_levels": [],
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tx_hash_buy": tx_hash,
        "tx_hash_sell": "",
        "close_reason": "",
    }
    positions.append(position)
    save_positions(positions)

    _add_trade_history({
        "type": "buy",
        "chat_id": chat_id,
        "token_address": token_address,
        "symbol": symbol,
        "amount_sol": amount_sol,
        "amount_tokens": amount_tokens,
        "price": entry_price,
        "tx_hash": tx_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return position


def update_position_price(token_address: str, current_price: float) -> List[Dict]:
    positions = load_positions()
    alerts = []

    for pos in positions:
        if pos["token_address"] == token_address and pos["status"] == "open":
            entry = pos["entry_price"]
            if entry > 0:
                pnl_pct = ((current_price - entry) / entry) * 100
                pnl_sol = pos["amount_sol"] * (pnl_pct / 100)
            else:
                pnl_pct = 0
                pnl_sol = 0

            pos["current_price"] = current_price
            pos["pnl_pct"] = round(pnl_pct, 2)
            pos["pnl_sol"] = round(pnl_sol, 4)
            if current_price > pos.get("highest_price", 0):
                pos["highest_price"] = current_price
            pos["updated_at"] = datetime.now(timezone.utc).isoformat()

            alerts.append(pos)

    save_positions(positions)
    return alerts


def close_position(position_id: str, exit_price: float, tx_hash: str = "", reason: str = "manual") -> Optional[Dict]:
    positions = load_positions()

    for pos in positions:
        if pos["id"] == position_id and pos["status"] == "open":
            entry = pos["entry_price"]
            if entry > 0:
                pnl_pct = ((exit_price - entry) / entry) * 100
                pnl_sol = pos["amount_sol"] * (pnl_pct / 100)
            else:
                pnl_pct = 0
                pnl_sol = 0

            pos["status"] = "closed"
            pos["exit_price"] = exit_price
            pos["pnl_pct"] = round(pnl_pct, 2)
            pos["pnl_sol"] = round(pnl_sol, 4)
            pos["closed_at"] = datetime.now(timezone.utc).isoformat()
            pos["tx_hash_sell"] = tx_hash
            pos["close_reason"] = reason

            save_positions(positions)

            _add_trade_history({
                "type": "sell",
                "chat_id": pos["chat_id"],
                "token_address": pos["token_address"],
                "symbol": pos["symbol"],
                "amount_sol": pos["amount_sol"],
                "pnl_pct": pos["pnl_pct"],
                "pnl_sol": pos["pnl_sol"],
                "price": exit_price,
                "reason": reason,
                "tx_hash": tx_hash,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return pos

    return None


def get_open_positions(chat_id: str = "") -> List[Dict]:
    positions = load_positions()
    if chat_id:
        return [p for p in positions if p["status"] == "open" and p["chat_id"] == chat_id]
    return [p for p in positions if p["status"] == "open"]


def get_position(token_address: str, chat_id: str = "") -> Optional[Dict]:
    positions = load_positions()
    for p in positions:
        if p["token_address"] == token_address and p["status"] == "open":
            if not chat_id or p["chat_id"] == chat_id:
                return p
    return None


def _add_trade_history(entry: Dict):
    history = load_trade_history()
    history.append(entry)
    if len(history) > 200:
        history = history[-100:]
    save_trade_history(history)


def get_trade_stats(chat_id: str = "") -> Dict:
    history = load_trade_history()
    if chat_id:
        history = [h for h in history if h.get("chat_id") == chat_id]

    buys = [h for h in history if h.get("type") == "buy"]
    sells = [h for h in history if h.get("type") == "sell"]

    wins = [s for s in sells if s.get("pnl_pct", 0) > 0]
    losses = [s for s in sells if s.get("pnl_pct", 0) < 0]

    total_pnl = sum(s.get("pnl_sol", 0) for s in sells)
    win_rate = (len(wins) / len(sells) * 100) if sells else 0

    return {
        "total_trades": len(buys),
        "open_positions": len(get_open_positions(chat_id)),
        "closed_trades": len(sells),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl_sol": round(total_pnl, 4),
    }
