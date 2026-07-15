import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

from config import NVIDIA_API_KEY, MIN_SCORE_FOR_ALERT

logger = logging.getLogger("memecoin-bot")

SIGNALS_FILE = Path(__file__).parent.parent / "data" / "signals_history.json"
SENT_FILE = Path(__file__).parent.parent / "data" / "sent_tokens.json"
PENDING_FILE = Path(__file__).parent.parent / "data" / "pending_signals.json"

AUTO_SIGNAL_INTERVAL = 300
AUTO_SIGNAL_MAX_PER_CYCLE = 3
AUTO_SIGNAL_MIN_SCORE = 70
AUTO_SIGNAL_COOLDOWN = 3600

# Fix: previously only the top (MAX_PER_CYCLE * 2) = 6 scored tokens were
# even given to the AI each cycle; anything ranked below that was silently
# dropped forever, every cycle, regardless of how good it was. This raises
# how many qualifying tokens get analyzed per cycle. Higher = fewer missed
# signals during busy markets, but more MiMo API calls/cost per cycle.
AUTO_SIGNAL_ANALYSIS_LIMIT = 15

# How long a confirmed BUY/STRONG_BUY signal is allowed to sit in the queue
# waiting for send-cap room before we consider its price data too stale to
# trust (3 cycles at the default 300s interval).
PENDING_MAX_AGE_SECONDS = 900

_running = True


def set_auto_running(val: bool):
    global _running
    _running = val


def is_auto_running() -> bool:
    return _running


def load_sent_tokens() -> Dict:
    if SENT_FILE.exists():
        try:
            return json.loads(SENT_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_sent_tokens(data: Dict):
    SENT_FILE.parent.mkdir(exist_ok=True, parents=True)
    SENT_FILE.write_text(json.dumps(data, indent=2))


def load_pending() -> List[Dict]:
    if PENDING_FILE.exists():
        try:
            return json.loads(PENDING_FILE.read_text())
        except Exception:
            return []
    return []


def save_pending(items: List[Dict]):
    PENDING_FILE.parent.mkdir(exist_ok=True, parents=True)
    try:
        PENDING_FILE.write_text(json.dumps(items, indent=2, default=str))
    except Exception as e:
        logger.error(f"Failed to save pending signal queue: {e}")


def save_signal_history(entry: Dict):
    SIGNALS_FILE.parent.mkdir(exist_ok=True, parents=True)
    history = []
    if SIGNALS_FILE.exists():
        try:
            history = json.loads(SIGNALS_FILE.read_text())
        except Exception:
            history = []
    history.append(entry)
    if len(history) > 100:
        history = history[-50:]
    SIGNALS_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False, default=str))


def get_recent_signals(hours: int = 24) -> List[Dict]:
    if not SIGNALS_FILE.exists():
        return []
    try:
        history = json.loads(SIGNALS_FILE.read_text())
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    return [s for s in reversed(history) if s.get("timestamp", 0) > cutoff][:20]


async def start_auto_signal():
    global _running
    logger.info("Auto signal broadcaster started")

    from core.deep_scanner import deep_scan
    from analyzers.safety import check_safety
    from analyzers.liquidity import analyze_liquidity
    from analyzers.holder import analyze_holder_distribution
    from analyzers.scorer import calculate_social_score, calculate_final_score
    from analyzers.professional import determine_signal
    from core.ai_analyzer import analyze_with_ai
    from core.whale_detector import detect_whales_for_token
    from core.deployer_check import analyze_token_deployer
    from core.bundler_detector import detect_bundler_activity
    from core.whale_tracker import check_whale_holds_token
    from alerts.charts import generate_charts_for_token
    from alerts.telegram import get_active_chat_ids

    cycle = 0

    while _running:
        try:
            cycle += 1
            logger.info(f"Auto signal cycle #{cycle}")

            from core.feedback_tracker import refresh_open_signals
            await refresh_open_signals()

            # Fix #6: re-tune score weights from real trade outcomes every
            # 12 cycles (~1 hour at the default 300s interval) — frequent
            # enough to adapt, infrequent enough not to thrash on noise.
            if cycle % 12 == 0:
                try:
                    from analyzers.weight_tuner import tune_weights_from_feedback
                    tune_weights_from_feedback()
                except Exception as e:
                    logger.error(f"Weight tuning error: {e}")

            pairs = await deep_scan(max_age_minutes=120, max_results=40)

            results = []
            for pair in pairs[:30]:
                try:
                    token_address = pair.get("base_token", {}).get("address", "")
                    if not token_address:
                        continue

                    liq = pair.get("liquidity_usd", 0)
                    mcap = pair.get("market_cap", 0)
                    if liq < 1000 or mcap < 500:
                        continue

                    safety_result = await check_safety(token_address)
                    liquidity_result = analyze_liquidity(pair)
                    holder_result = await analyze_holder_distribution(token_address)
                    social_result = await calculate_social_score(pair)
                    score = await calculate_final_score(safety_result, liquidity_result, holder_result, social_result, pair)

                    age_minutes = pair.get("age_minutes", 0)
                    now = datetime.now(timezone.utc)
                    created = pair.get("created_at")
                    if not age_minutes and created:
                        age_minutes = (now - datetime.fromtimestamp(created / 1000, tz=timezone.utc)).total_seconds() / 60

                    result = {
                        "name": pair.get("base_token", {}).get("name", "Unknown"),
                        "symbol": pair.get("base_token", {}).get("symbol", "???"),
                        "token_address": token_address,
                        "pair_address": pair.get("pair_address", ""),
                        "price_usd": pair.get("price_usd", 0),
                        "liquidity_usd": liq,
                        "market_cap": mcap,
                        "volume_24h": pair.get("volume_24h", 0),
                        "price_change_24h": pair.get("price_change", {}).get("h24") if isinstance(pair.get("price_change"), dict) else None,
                        "url": pair.get("url", ""),
                        "dex": pair.get("dex", ""),
                        "age_minutes": age_minutes,
                        "score": score,
                    }

                    if token_address:
                        deployer = await analyze_token_deployer(token_address)
                        result["deployer_check"] = deployer
                        auto_whales = await detect_whales_for_token(token_address, max_holders=20)
                        result["auto_whales"] = auto_whales
                        if age_minutes < 30:
                            result["bundler_check"] = await detect_bundler_activity(token_address)
                        result["whale_holders"] = await check_whale_holds_token(token_address)

                        if deployer.get("found"):
                            stats = deployer.get("stats", {})
                            if stats.get("status") == "trusted":
                                result["score"]["total_score"] = min(100, result["score"]["total_score"] + 5)
                            elif stats.get("status") == "suspicious":
                                result["score"]["total_score"] = max(0, result["score"]["total_score"] - 15)

                        from core.smart_money import analyze_smart_money, record_early_buyers
                        from core.narratives import classify_narrative

                        result["narratives"] = classify_narrative(
                            pair.get("base_token", {}).get("name", ""),
                            pair.get("base_token", {}).get("symbol", ""),
                        )

                        early = []
                        for w in auto_whales.get("whales", []):
                            if w.get("wallet"):
                                early.append(w["wallet"])
                        for w in auto_whales.get("dolphins", []):
                            if w.get("wallet"):
                                early.append(w["wallet"])
                        launch_at = None
                        created = pair.get("created_at")
                        if created:
                            launch_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
                        record_early_buyers(token_address, launch_at, early)

                        sm = await analyze_smart_money(token_address)
                        result["smart_money"] = sm
                        if sm.get("score_adjustment"):
                            result["score"]["total_score"] = max(0, min(100, result["score"]["total_score"] + sm["score_adjustment"]))

                    result["professional"] = determine_signal(result)

                    if result["score"]["total_score"] >= AUTO_SIGNAL_MIN_SCORE:
                        results.append(result)

                except Exception as e:
                    logger.error(f"Scan error for {pair.get('base_token', {}).get('symbol', '?')}: {e}")
                    continue

            results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

            sent_tokens = load_sent_tokens()
            now_ts = datetime.now(timezone.utc).timestamp()
            sent_count = 0

            # --- Phase 1: flush anything queued from a previous cycle first,
            # so it doesn't get starved out by a fresh batch of new tokens.
            # These are NEVER auto-bought here — only fresh, this-cycle data
            # is trusted enough to spend real SOL on (see phase 2). Queued
            # items only guarantee the *alert* isn't lost.
            pending = load_pending()
            pending = [p for p in pending if now_ts - p.get("queued_at", 0) <= PENDING_MAX_AGE_SECONDS]
            still_pending = []

            for item in pending:
                addr = item.get("token_address", "")
                if sent_count >= AUTO_SIGNAL_MAX_PER_CYCLE:
                    still_pending.append(item)
                    continue
                if now_ts - sent_tokens.get(addr, 0) < AUTO_SIGNAL_COOLDOWN:
                    continue  # got sent via another path already, drop it

                r = item["result"]
                ai_result = item["ai_result"]
                r["charts"] = await generate_charts_for_token(r)

                from alerts.telegram import send_ai_signal
                await send_ai_signal(r, ai_result)

                sent_tokens[addr] = now_ts
                sent_count += 1

                save_signal_history({
                    "symbol": r["symbol"],
                    "token": addr,
                    "score": r["score"]["total_score"],
                    "signal": ai_result["signal"],
                    "confidence": ai_result["confidence"],
                    "price_usd": r.get("price_usd", 0),
                    "mcap": r.get("market_cap", 0),
                    "reasoning": ai_result.get("reasoning", "")[:200],
                    "timestamp": now_ts,
                    "source": ai_result.get("source", "ai"),
                })

                deferred_by = int(now_ts - item.get("queued_at", now_ts))
                logger.info(f"Signal sent from queue (deferred {deferred_by}s): {r['symbol']} ({ai_result['signal']}, {ai_result['confidence']}/10)")

                from core.feedback_tracker import record_signal
                record_signal(
                    token_address=addr,
                    symbol=r["symbol"],
                    signal=ai_result["signal"],
                    confidence=ai_result["confidence"],
                    price_at_signal=r.get("price_usd", 0),
                    score=r["score"]["total_score"],
                    reasoning=ai_result.get("reasoning", ""),
                    score_breakdown=r["score"].get("breakdown", {}),
                )

            pending_addrs = {p["token_address"] for p in still_pending}

            # --- Phase 2: analyze this cycle's fresh results. No more
            # results[:MAX*2] truncation — every qualifying token gets a
            # chance (bounded by AUTO_SIGNAL_ANALYSIS_LIMIT), instead of
            # anything ranked below the old top-6 cutoff being silently
            # dropped forever.
            for r in results[:AUTO_SIGNAL_ANALYSIS_LIMIT]:
                addr = r.get("token_address", "")
                if not addr:
                    continue

                if addr in pending_addrs:
                    continue  # already queued from a previous cycle, don't re-analyze

                last_sent = sent_tokens.get(addr, 0)
                if now_ts - last_sent < AUTO_SIGNAL_COOLDOWN:
                    continue

                pro = r.get("professional", {})
                if pro.get("signal") == "AVOID":
                    continue

                ai_result = await analyze_with_ai(r)
                r["ai_analysis"] = ai_result

                if ai_result.get("signal") not in ("STRONG_BUY", "BUY"):
                    continue

                if sent_count >= AUTO_SIGNAL_MAX_PER_CYCLE:
                    # Confirmed buy signal, but no room left this cycle.
                    # Queue it with priority instead of dropping it.
                    still_pending.append({
                        "token_address": addr,
                        "result": r,
                        "ai_result": ai_result,
                        "queued_at": now_ts,
                    })
                    pending_addrs.add(addr)
                    logger.info(f"Signal queued (cycle cap reached): {r['symbol']} ({ai_result['signal']}, {ai_result['confidence']}/10)")
                    continue

                r["charts"] = await generate_charts_for_token(r)

                from alerts.telegram import send_ai_signal
                await send_ai_signal(r, ai_result)

                sent_tokens[addr] = now_ts
                sent_count += 1

                save_signal_history({
                    "symbol": r["symbol"],
                    "token": addr,
                    "score": r["score"]["total_score"],
                    "signal": ai_result["signal"],
                    "confidence": ai_result["confidence"],
                    "price_usd": r.get("price_usd", 0),
                    "mcap": r.get("market_cap", 0),
                    "reasoning": ai_result.get("reasoning", "")[:200],
                    "timestamp": now_ts,
                    "source": ai_result.get("source", "ai"),
                })

                logger.info(f"Signal sent: {r['symbol']} ({ai_result['signal']}, {ai_result['confidence']}/10)")

                from core.feedback_tracker import record_signal
                record_signal(
                    token_address=addr,
                    symbol=r["symbol"],
                    signal=ai_result["signal"],
                    confidence=ai_result["confidence"],
                    price_at_signal=r.get("price_usd", 0),
                    score=r["score"]["total_score"],
                    reasoning=ai_result.get("reasoning", ""),
                    score_breakdown=r["score"].get("breakdown", {}),
                )

                from core.trade_executor import auto_buy_signal
                from core.wallet_manager import get_all_active_wallets
                active_wallets = get_all_active_wallets()
                for wallet in active_wallets:
                    try:
                        buy_result = await auto_buy_signal(wallet["chat_id"], r, ai_result)
                        if buy_result and buy_result.get("success"):
                            logger.info(f"Auto buy: {r['symbol']} for chat {wallet['chat_id']}")
                    except Exception as e:
                        logger.error(f"Auto buy error: {e}")

            save_pending(still_pending)
            save_sent_tokens(sent_tokens)

            await asyncio.sleep(AUTO_SIGNAL_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Auto signal error: {e}")
            await asyncio.sleep(60)

    logger.info("Auto signal broadcaster stopped")
