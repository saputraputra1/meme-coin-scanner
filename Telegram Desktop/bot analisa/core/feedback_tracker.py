import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("memecoin-bot")

FEEDBACK_FILE = Path(__file__).parent.parent / "data" / "signal_feedback.json"

# Fix #1/#2: minimum number of *closed* signals before we trust win-rate enough
# to adjust confidence. 5 was statistically meaningless for volatile assets.
MIN_CLOSED_SIGNALS_FOR_ADJUSTMENT = 30

# Real exit reasons from rug_monitor.py — used to reconcile feedback outcomes
# with what actually happened to the money, instead of an arbitrary 24h/±20%
# price snapshot that has nothing to do with the bot's real stop-loss/take-profit.
LOSS_CLOSE_REASONS = {"stop_loss", "rug_detected"}
WIN_CLOSE_REASONS = {"take_profit_50%", "trailing_stop"}


def load_feedback() -> Dict:
    if FEEDBACK_FILE.exists():
        try:
            return json.loads(FEEDBACK_FILE.read_text())
        except Exception:
            return {"signals": [], "stats": {}}
    return {"signals": [], "stats": {}}


def save_feedback(feedback: Dict):
    FEEDBACK_FILE.parent.mkdir(exist_ok=True, parents=True)
    if len(feedback["signals"]) > 500:
        feedback["signals"] = feedback["signals"][-250:]
    FEEDBACK_FILE.write_text(json.dumps(feedback, indent=2, ensure_ascii=False, default=str))


def record_signal(token_address: str, symbol: str, signal: str, confidence: int,
                  price_at_signal: float, score: int, reasoning: str,
                  score_breakdown: Optional[Dict] = None):
    feedback = load_feedback()
    feedback["signals"].append({
        "token": token_address,
        "symbol": symbol,
        "signal": signal,
        "confidence": confidence,
        "price_at_signal": price_at_signal,
        "score": score,
        # Fix #6: keep the per-component breakdown (safety/liquidity/holders/
        # social) at signal time so we can later measure which components
        # actually correlated with wins vs losses, instead of tuning weights
        # by guesswork.
        "score_breakdown": score_breakdown or {},
        "reasoning": reasoning[:200],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open",
        "price_after_1h": None,
        "price_after_6h": None,
        "price_after_24h": None,
        "max_price": price_at_signal,
        "min_price": price_at_signal,
        "outcome": None,
    })
    save_feedback(feedback)


def _find_real_exit(token_address: str, signal_timestamp: str) -> Optional[Dict]:
    """Fix #1: look up the bot's actual trade_history for a sell on this token
    that happened after the signal was issued, so feedback reflects real P&L
    and the real reason (stop_loss/take_profit/rug_detected/...) instead of a
    generic 24h/±20% price snapshot that ignores how the bot actually trades."""
    try:
        from core.position_tracker import load_trade_history
    except Exception:
        return None

    try:
        sig_dt = datetime.fromisoformat(signal_timestamp)
    except Exception:
        return None

    history = load_trade_history()
    candidates = []
    for h in history:
        if h.get("type") != "sell" or h.get("token_address") != token_address:
            continue
        try:
            sell_dt = datetime.fromisoformat(h.get("timestamp", ""))
        except Exception:
            continue
        if sell_dt >= sig_dt:
            candidates.append((sell_dt, h))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    _, sell = candidates[0]
    return {
        "pnl_pct": sell.get("pnl_pct", 0),
        "reason": sell.get("reason", "manual"),
        "price": sell.get("price", 0),
    }


def update_feedback_prices(token_address: str, current_price: float):
    feedback = load_feedback()
    now = datetime.now(timezone.utc)
    updated = False

    for sig in feedback["signals"]:
        if sig["token"] != token_address or sig["status"] != "open":
            continue

        sig_time = datetime.fromisoformat(sig["timestamp"])
        hours_since = (now - sig_time).total_seconds() / 3600

        if sig["price_after_1h"] is None and hours_since >= 1:
            sig["price_after_1h"] = current_price
            updated = True

        if sig["price_after_6h"] is None and hours_since >= 6:
            sig["price_after_6h"] = current_price
            updated = True

        if sig["price_after_24h"] is None and hours_since >= 24:
            sig["price_after_24h"] = current_price
            updated = True

        if current_price > sig.get("max_price", 0):
            sig["max_price"] = current_price
        if current_price < sig.get("min_price", float("inf")):
            sig["min_price"] = current_price

        if sig["outcome"] is None:
            real_exit = _find_real_exit(token_address, sig["timestamp"])

            if real_exit is not None:
                pnl = real_exit["pnl_pct"]
                reason = real_exit["reason"]
                if reason in LOSS_CLOSE_REASONS or pnl < 0:
                    outcome = "loss"
                elif reason in WIN_CLOSE_REASONS or pnl > 0:
                    outcome = "win"
                else:
                    outcome = "neutral"

                sig["outcome"] = outcome
                sig["status"] = "closed"
                sig["final_pnl"] = round(pnl, 2)
                sig["close_reason"] = reason
                sig["outcome_source"] = "real_trade"
                updated = True

            elif hours_since >= 24:
                # No real trade was ever executed for this signal (e.g. no
                # wallet linked / auto-trade off) — fall back to a price
                # snapshot, but mark it clearly as a proxy, not a real result.
                entry = sig["price_at_signal"]
                if entry > 0:
                    pnl = ((current_price - entry) / entry) * 100
                    if pnl >= 20:
                        outcome = "win"
                    elif pnl <= -20:
                        outcome = "loss"
                    else:
                        outcome = "neutral"
                    sig["outcome"] = outcome
                    sig["status"] = "closed"
                    sig["final_pnl"] = round(pnl, 2)
                    sig["outcome_source"] = "price_snapshot_proxy"
                    updated = True

    if updated:
        save_feedback(feedback)


async def refresh_open_signals():
    """Fix #1/#6 groundwork: without this, every open signal stays 'open'
    forever and get_performance_stats()/get_confidence_adjustment() never see
    real data. Walks all open signals, checks trade_history first (real
    exit), then falls back to a live price lookup."""
    from core.dexscreener import get_token_info

    feedback = load_feedback()
    open_tokens = {s["token"] for s in feedback["signals"] if s["status"] == "open"}

    for token_address in open_tokens:
        try:
            info = await get_token_info(token_address)
            current_price = info.get("price_usd", 0) if info else 0
            if current_price:
                update_feedback_prices(token_address, current_price)
        except Exception as e:
            logger.error(f"refresh_open_signals price lookup failed for {token_address}: {e}")


def get_performance_stats() -> Dict:
    feedback = load_feedback()
    signals = feedback.get("signals", [])

    closed = [s for s in signals if s.get("status") == "closed"]
    if not closed:
        return _default_stats()

    wins = [s for s in closed if s.get("outcome") == "win"]
    losses = [s for s in closed if s.get("outcome") == "loss"]
    neutral = [s for s in closed if s.get("outcome") == "neutral"]

    total = len(closed)
    win_rate = len(wins) / total * 100 if total > 0 else 0
    avg_win = sum(s.get("final_pnl", 0) for s in wins) / len(wins) if wins else 0
    avg_loss = sum(s.get("final_pnl", 0) for s in losses) / len(losses) if losses else 0

    by_confidence = {}
    for s in closed:
        conf = s.get("confidence", 5)
        if conf not in by_confidence:
            by_confidence[conf] = {"wins": 0, "losses": 0, "total": 0}
        by_confidence[conf]["total"] += 1
        if s.get("outcome") == "win":
            by_confidence[conf]["wins"] += 1
        elif s.get("outcome") == "loss":
            by_confidence[conf]["losses"] += 1

    best_confidence = max(by_confidence.items(), key=lambda x: x[1]["wins"] / max(x[1]["total"], 1), default=(7, {}))

    # Fix #6 groundwork: expectancy accounts for win/loss *size*, not just how
    # often we win. A 70% win-rate with tiny wins and rare huge losses can be
    # worse than a 40% win-rate with big wins — win_rate alone hides this.
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    real_trade_closed = [s for s in closed if s.get("outcome_source") == "real_trade"]

    return {
        "total_signals": len(signals),
        "closed_signals": total,
        "real_trade_signals": len(real_trade_closed),
        "wins": len(wins),
        "losses": len(losses),
        "neutral": len(neutral),
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 1),
        "avg_loss_pct": round(avg_loss, 1),
        "expectancy_pct": round(expectancy, 2),
        "best_confidence": best_confidence[0],
        "by_confidence": by_confidence,
        "recent_signals": [_summarize_signal(s) for s in signals[-10:]],
    }


def _summarize_signal(sig: Dict) -> Dict:
    return {
        "symbol": sig.get("symbol", "?"),
        "signal": sig.get("signal", "?"),
        "confidence": sig.get("confidence", 0),
        "outcome": sig.get("outcome", "open"),
        "pnl": sig.get("final_pnl"),
    }


def _default_stats() -> Dict:
    return {
        "total_signals": 0,
        "closed_signals": 0,
        "real_trade_signals": 0,
        "wins": 0,
        "losses": 0,
        "neutral": 0,
        "win_rate": 0,
        "avg_win_pct": 0,
        "avg_loss_pct": 0,
        "expectancy_pct": 0,
        "best_confidence": 7,
        "by_confidence": {},
        "recent_signals": [],
    }


def get_confidence_adjustment() -> int:
    """Fix #2: require a statistically meaningful sample (30, not 5) before
    trusting historical performance enough to move confidence. Fix #6
    groundwork: gate on expectancy (win rate AND win/loss size), since a high
    win-rate with poor expectancy shouldn't be rewarded with more confidence."""
    stats = get_performance_stats()
    if stats["closed_signals"] < MIN_CLOSED_SIGNALS_FOR_ADJUSTMENT:
        return 0

    win_rate = stats["win_rate"]
    expectancy = stats["expectancy_pct"]

    if win_rate >= 70 and expectancy > 0:
        return 1
    elif win_rate <= 30 or expectancy < 0:
        return -1
    return 0
