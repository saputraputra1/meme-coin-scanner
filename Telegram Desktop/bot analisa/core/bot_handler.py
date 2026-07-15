import asyncio
import sys
import os
import logging
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger("memecoin-bot")


def _format_top_holders(holders: dict) -> str:
    top_holders = holders.get("top_holders", [])
    if not top_holders:
        return ""
    lines = ["\n👥 *Top Holders:*"]
    for i, h in enumerate(top_holders[:10], 1):
        addr = h.get("address", "?")
        pct = h.get("pct", 0)
        short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
        link = f"https://solscan.io/account/{addr}"
        whale = "🐋" if pct >= 5 else "🐬" if pct >= 2 else "🐟"
        lines.append(f"  {i}. {whale} {pct:.1f}% — [{short}]({link})")
    return "\n".join(lines)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TELEGRAM_BOT_TOKEN, MIN_SCORE_FOR_ALERT
from core.dexscreener import fetch_trending_solana, get_token_info
from core.pumpfun import fetch_new_launches
from core.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist
from core.whale_tracker import load_known_whales, add_whale, remove_whale, scan_whale_buys, scan_whale_portfolios
from core.bundler_detector import detect_bundler_activity
from core.volume_tracker import detect_spikes, load_history
from core.migration_alert import detect_migrations_from_scan
from core.deployer_check import analyze_token_deployer, get_deployer_stats
from core.deployer_tracker import load_deployer_list, add_deployer, remove_deployer, scan_deployer_new_tokens
from analyzers.safety import check_safety
from analyzers.liquidity import analyze_liquidity
from analyzers.holder import analyze_holder_distribution
from analyzers.scorer import calculate_social_score, calculate_final_score
from alerts.telegram import get_active_chat_ids, detect_new_chats
from utils.telegram_client import create_bot
from utils.export import export_csv


async def analyze_token(pair_data: dict) -> dict:
    token_address = pair_data.get("base_token", {}).get("address", "")

    safety_result = await check_safety(token_address)
    liquidity_result = analyze_liquidity(pair_data)
    holder_result = await analyze_holder_distribution(token_address)
    social_result = await calculate_social_score(pair_data)
    score = await calculate_final_score(safety_result, liquidity_result, holder_result, social_result, pair_data)

    age_minutes = pair_data.get("age_minutes", 0)
    if not age_minutes:
        now = datetime.now(timezone.utc)
        created = pair_data.get("created_at")
        if created:
            age_minutes = (now - datetime.fromtimestamp(created / 1000, tz=timezone.utc)).total_seconds() / 60

    result = {
        "name": pair_data.get("base_token", {}).get("name", "Unknown"),
        "symbol": pair_data.get("base_token", {}).get("symbol", "???"),
        "token_address": token_address,
        "pair_address": pair_data.get("pair_address", ""),
        "price_usd": pair_data.get("price_usd", 0),
        "liquidity_usd": pair_data.get("liquidity_usd", 0),
        "market_cap": pair_data.get("market_cap", 0),
        "volume_24h": pair_data.get("volume_24h", 0),
        "price_change_24h": pair_data.get("price_change", {}).get("h24") if isinstance(pair_data.get("price_change"), dict) else None,
        "url": pair_data.get("url", ""),
        "dex": pair_data.get("dex", ""),
        "age_minutes": age_minutes,
        "score": score,
    }

    if token_address:
        from core.whale_detector import detect_whales_for_token
        from core.deployer_check import analyze_token_deployer
        from core.onchain_metrics import get_onchain_metrics
        from core.social_tracker import get_social_sentiment
        from core.price_history import get_price_history
        from core.market_context import get_market_context
        from core.feedback_tracker import get_performance_stats
        from core.smart_money import analyze_smart_money, record_early_buyers
        from core.narratives import classify_narrative
        from analyzers.professional import determine_signal
        from alerts.charts import generate_charts_for_token

        deployer = await analyze_token_deployer(token_address)
        result["deployer_check"] = deployer

        auto_whales = await detect_whales_for_token(token_address, max_holders=20)
        result["auto_whales"] = auto_whales

        onchain = await get_onchain_metrics(token_address)
        result["onchain_metrics"] = onchain

        social = await get_social_sentiment(pair_data)
        result["social_sentiment"] = social

        price_hist = await get_price_history(token_address)
        result["price_history"] = price_hist

        market = await get_market_context()
        result["market_context"] = market

        feedback = get_performance_stats()
        result["feedback_stats"] = feedback

        if deployer.get("found"):
            stats = deployer.get("stats", {})
            if stats.get("status") == "trusted":
                result["score"]["total_score"] = min(100, result["score"]["total_score"] + 5)
            elif stats.get("status") == "suspicious":
                result["score"]["total_score"] = max(0, result["score"]["total_score"] - 15)

        result["narratives"] = classify_narrative(
            pair_data.get("base_token", {}).get("name", ""),
            pair_data.get("base_token", {}).get("symbol", ""),
        )

        if age_minutes < 120:
            early = []
            for w in auto_whales.get("whales", []):
                if w.get("wallet"):
                    early.append(w["wallet"])
            for w in auto_whales.get("dolphins", []):
                if w.get("wallet"):
                    early.append(w["wallet"])
            launch_at = None
            created = pair_data.get("created_at")
            if created:
                launch_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
            record_early_buyers(token_address, launch_at, early)

        sm = await analyze_smart_money(token_address)
        result["smart_money"] = sm
        if sm.get("score_adjustment"):
            result["score"]["total_score"] = max(0, min(100, result["score"]["total_score"] + sm["score_adjustment"]))
            result["score"]["smart_money_adj"] = sm["score_adjustment"]

        result["professional"] = determine_signal(result)
        result["charts"] = generate_charts_for_token(result)

    return result


def format_telegram_message(result: Dict) -> str:
    score_data = result.get("score", {})
    total = score_data.get("total_score", 0)
    details = score_data.get("details", {})
    safety = details.get("safety", {})
    safety_checks = safety.get("checks", {})
    liquidity = details.get("liquidity", {})
    holders = details.get("holders", {})
    social = details.get("social", {})
    age = result.get("age_minutes", "?")
    pro = result.get("professional", {})
    deployer = result.get("deployer_check", {}).get("stats", {})
    bundler = result.get("bundler_check", {})

    mcap = liquidity.get("market_cap", 0)
    liq = liquidity.get("liquidity_usd", 0)
    signal = pro.get("signal", "BUY")
    signal_label = pro.get("signal_label", signal)
    confidence = pro.get("confidence", "?")
    position = pro.get("position_recommendation", "N/A")
    concerns = pro.get("concerns", [])
    positives = pro.get("positives", [])
    summary = pro.get("summary", "")

    sig_emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(signal, "❓")

    mint = "✅" if safety_checks.get("mint_authority") else "⚠️"
    freeze = "✅" if safety_checks.get("freeze_authority") else "⚠️"
    honeypot = safety_checks.get("honeypot_detected", False)
    hp_text = "🛑 YES" if honeypot is True else "✅ No"
    age_str = f"{age:.0f}m" if isinstance(age, (int, float)) else str(age)
    deployer_status = deployer.get("status", "unknown")
    deployer_rug = deployer.get("rug_count", 0)
    deployer_rep = deployer.get("reputation_score", 0)
    bundler_count = bundler.get("rapid_buys_under_60s", 0) if bundler else 0
    holder_total = holders.get("total_holders", "?")
    top10 = holders.get("top10_concentration_pct", "?")
    holder_health = holders.get("health", "?")

    price_ch = result.get("price_change_24h", 0) or 0
    pc_emoji = "📈" if price_ch > 0 else "📉" if price_ch < 0 else "➖"

    return (
        f"{sig_emoji} *{signal_label}* | *{result.get('symbol', '???')}* — {result.get('name', 'Unknown')}\n"
        f"Score: {total}/100 | Confidence: {confidence}/10 | {position}\n"
        f"{'─' * 25}\n"
        f"💰 ${mcap:,.0f} MCap | ${liq:,.0f} Liq | {pc_emoji} {price_ch:+.0f}%\n"
        f"🔒 Mint: {mint} | Freeze: {freeze} | HP: {hp_text}\n"
        f"👥 Holders: {holder_total} | Top10: {top10}% | Health: {holder_health}\n"
        f"🌐 Social: {', '.join(social.get('links', [])) or '-'}"
        + (f" | @{social.get('twitter_handle')}" if social.get('twitter_handle') else "")
        + f"\n" +
        (f"🕵️ Deployer: {deployer_status} ({deployer_rep}/100) | rug: {deployer_rug}\n" if deployer_status not in ("unknown", "UNKNOWN") or deployer_rug else "") +
        (f"📦 Bundler: {bundler_count} rapid buys\n" if bundler_count > 0 else "") +
        (f"\n✅ {', '.join(positives[:3])}" if positives else "") +
        (f"\n❌ {', '.join(concerns[:3])}" if concerns else "") +
          f"\n{'─' * 25}\n"
          f"💡 {summary}\n"
          f"{_format_top_holders(holders)}\n"
          f"⏱️ {age_str} | [Chart]({result.get('url', '')})"
      )


async def handle_command(command: str, chat_id: str, args: str = "") -> str:
    print(f"[Bot] /{command} from {chat_id}" + (f" args: {args}" if args else ""))

    handlers = {
        "start": cmd_start,
        "scan": cmd_scan,
        "live": cmd_live,
        "pumpfun": cmd_pumpfun,
        "score": cmd_score,
        "chats": cmd_chats,
        "help": cmd_help,
        "wl": cmd_watchlist,
        "watchlist": cmd_watchlist,
        "wladd": cmd_wl_add,
        "wlremove": cmd_wl_remove,
        "export": cmd_export,
        "filter": cmd_filter,
        "whale": cmd_whale_scan,
        "whales": cmd_whale_scan,
        "whaleadd": cmd_whale_add,
        "whaleremove": cmd_whale_remove,
        "whalefolio": cmd_whale_portfolio,
        "deepscan": cmd_deepscan,
        "autoscan": cmd_autoscan,
        "autostatus": cmd_autostatus,
        "signals": cmd_signals,
        "ai": cmd_ai_analysis,
        "gem": cmd_gem_hunter,
        "wallet": cmd_wallet,
        "autotrade": cmd_autotrade,
        "buy": cmd_buy,
        "sell": cmd_sell,
        "positions": cmd_positions,
          "rugcheck": cmd_rugcheck,
          "rughistory": cmd_rughistory,
          "compare": cmd_compare,
        "verify": cmd_verify_token,
        "report": cmd_report,
        "sellmode": cmd_sell_mode,
        "perf": cmd_performance,
        "bundler": cmd_bundler,
        "spikes": cmd_spikes,
        "deployer": cmd_deployer,
        "deployers": cmd_deployers_list,
        "deployeradd": cmd_deployer_add,
        "smartmoney": cmd_smart_money,
        "narratives": cmd_narratives,
    }

    handler = handlers.get(command)
    if handler:
        try:
            return await handler(chat_id, args)
        except Exception as e:
            print(f"[Bot] Error in /{command}: {e}")
            return f"Error processing /{command}: {str(e)[:200]}"
    return "Unknown command. Type /help for available commands."


async def cmd_start(chat_id: str, args: str) -> str:
    from alerts.telegram import _auto_chats, _save_auto_chats, _load_auto_chats

    _load_auto_chats()
    if chat_id not in _auto_chats:
        _auto_chats.add(chat_id)
        _save_auto_chats()

    return (
        "🚀 *Meme Coin Scanner Bot*\n"
        "Mencari meme coin potensial di Solana\n"
        "\n"
        "*Discovery:*\n"
        "/scan — Quick scan trending token\n"
        "/deepscan — Deep scan 50+ coins from 4 sources\n"
        "/filter <preset> — Custom filter (aggressive/balanced/conservative)\n"
        "/pumpfun — Scan Pump.fun launches\n"
        "/score <addr> — Analisis token by address\n"
        "/ai <addr> — AI analysis + charts\n"
        "/gem — Gem hunter: cari koin potensial naik ribuan %\n"
        "\n"
        "*Safety & Monitoring:*\n"
        "/live — Mulai/stop live monitoring\n"
        "/rughistory — Database riwayat rug deployer\n"
        "/rugcheck <addr> — Deteksi rug real-time\n"
        "/spikes — Cek volume spike terbaru\n"
        "/bundler <addr> — Deteksi aktivitas bundler/insider\n"
        "\n"
        "*AI Auto Signal:*\n"
        "/autoscan on/off — Aktifkan/matikan auto signal AI\n"
        "/autostatus — Status auto signal + sinyal terbaru\n"
        "/signals — Riwayat sinyal 24 jam + reasoning\n"
        "\n"
        "*Watchlist:*\n"
        "/wl — View watchlist\n"
        "/wladd <addr> — Tambah ke watchlist\n"
        "/wlremove <addr> — Hapus dari watchlist\n"
        "\n"
        "*Whale Tracker:*\n"
        "/whales <token> — Auto-detect whale wallets\n"
        "/whalefolio — Portfolio semua whale\n"
        "/whaleadd <addr> — Track whale wallet\n"
        "/whaleremove <addr> — Untrack whale\n"
        "\n"
        "*Deployer Tools:*\n"
        "/deployer <addr> — Cek history creator token\n"
        "/deployers — View tracked deployers\n"
        "/deployeradd <addr> — Track deployer wallet\n"
        "\n"
        "*Lainnya:*\n"
        "/export — Export scan to CSV\n"
        "/chats — List chat terdaftar\n"
        "/help — Bantuan ini\n"
        "\n"
        "*Smart Money & Narratives:*\n"
        "/smartmoney <addr> — Cek smart money & insider selling\n"
        "/narratives — Sector momentum ranking\n"
        "\n"
        "🤖 Auto signal broadcast tiap 5 menit"
    )


async def cmd_scan(chat_id: str, args: str) -> str:
    try:
        pairs = await fetch_trending_solana()
    except Exception:
        return "❌ Gagal fetch data dari DexScreener."

    if not pairs:
        return "🔍 Tidak ada token trending ditemukan."

    results = []
    for pair in pairs[:15]:
        liq = pair.get("liquidity_usd", 0)
        mcap = pair.get("market_cap", 0)
        if liq < 3000 or mcap > 2000000:
            continue
        analyzed = await analyze_token(pair)
        results.append(analyzed)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    if not results:
        return "🔍 Tidak ada token memenuhi kriteria (liq > $3K, mcap < $2M)."

    lines = [f"🔍 *Quick Scan Results* ({len(results)} tokens)\n"]
    for r in results[:8]:
        s = r["score"]
        emoji = {"HOT": "🔥", "POTENTIAL": "🟢", "WATCH": "🟡", "CAUTION": "⬜"}.get(s["verdict"], "")
        lines.append(f"{emoji} *{r['symbol']}* — {s['total_score']}/100 | MCap: ${r['market_cap']:,.0f} | Liq: ${r['liquidity_usd']:,.0f} | Age: {r['age_minutes']:.0f}m")

    return "\n".join(lines)


_live_tasks: Dict[str, asyncio.Task] = {}


async def cmd_live(chat_id: str, args: str) -> str:
    if chat_id in _live_tasks:
        _live_tasks[chat_id].cancel()
        del _live_tasks[chat_id]
        return "⏹️ Live monitoring stopped."

    verbose = args.strip().lower() in ("v", "verbose", "debug")

    from telegram import Bot
    bot = create_bot(TELEGRAM_BOT_TOKEN)

    async def live_loop():
        LIVE_AI_MIN_SCORE = 80
        MIN_LIQUIDITY = 5000
        MIN_AI_CONFIDENCE = 6
        PRE_FILTER_LIQUIDITY = 500
        PRE_FILTER_VOLUME = 1000
        seen = set()
        cycle = 0
        logger.info(f"Live loop started for chat {chat_id} (verbose={verbose})")
        try:
            while True:
                cycle += 1
                if cycle % 5 == 0:
                    seen.clear()
                    logger.info(f"Cycle {cycle}: Reset seen set, re-scanning tokens")

                try:
                    from core.deep_scanner import deep_scan
                    pairs = await deep_scan(max_age_minutes=60, max_results=30)
                except Exception as e:
                    logger.error(f"Live fetch error: {e}")
                    await asyncio.sleep(30)
                    continue

                logger.info(f"Cycle {cycle}: Fetched {len(pairs)} tokens from 4 sources")

                new_pairs = [p for p in pairs if p.get("pair_address", "") not in seen]
                if not new_pairs:
                    logger.info(f"Cycle {cycle}: No new tokens (seen has {len(seen)} tokens)")
                    if cycle % 5 == 0 or cycle == 1:
                        heartbeat_emoji = "⏳"
                        lines = [f"{heartbeat_emoji} *Live Active* — Scan #{cycle}"]
                        lines.append("No new tokens found, waiting for next cycle...")
                        try:
                            await bot.send_message(chat_id=chat_id, text="\n".join(lines), disable_web_page_preview=True)
                        except Exception:
                            pass
                    await asyncio.sleep(60)
                    continue

                for pair in new_pairs:
                    addr = pair.get("pair_address", "")
                    seen.add(addr)

                    liq = pair.get("liquidity_usd", 0) or 0
                    vol = pair.get("volume_24h", 0) or 0
                    if liq < PRE_FILTER_LIQUIDITY and vol < PRE_FILTER_VOLUME:
                        continue

                    try:
                        analyzed = await analyze_token(pair)
                    except Exception as e:
                        logger.error(f"Analyze error for {addr}: {e}")
                        continue

                    total = analyzed["score"]["total_score"]
                    symbol = analyzed.get("symbol", "???")

                    if total >= MIN_SCORE_FOR_ALERT:
                        passed.append((symbol, total))
                        msg = format_telegram_message(analyzed)
                        from alerts.telegram import get_active_chat_ids
                        chat_ids = get_active_chat_ids()
                        for cid in chat_ids:
                            try:
                                await bot.send_message(chat_id=cid, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
                            except Exception as e:
                                logger.error(f"Live send error to {cid}: {e}")
                        logger.info(f"Score alert broadcast: {symbol} score={total} to {len(chat_ids)} chats")

                        if total >= LIVE_AI_MIN_SCORE and analyzed.get("liquidity_usd", 0) >= MIN_LIQUIDITY:
                            try:
                                from core.ai_analyzer import analyze_with_ai
                                ai_result = await analyze_with_ai(analyzed)
                                sig = ai_result.get("signal")
                                conf = ai_result.get("confidence", 0)
                                risk = ai_result.get("risk_level", "medium")
                                ttype = ai_result.get("trade_type", "SCALP")
                                if (
                                    sig in ("STRONG_BUY", "BUY")
                                    and isinstance(conf, (int, float)) and conf >= MIN_AI_CONFIDENCE
                                    and risk != "high"
                                    and ttype in ("HOLD", "SCALP+HOLD")
                                ):
                                    from alerts.telegram import send_ai_signal
                                    await send_ai_signal(analyzed, ai_result)
                                    logger.info(f"AI signal sent: {symbol} {sig} conf={conf}")
                            except Exception as e:
                                logger.error(f"AI analysis error for {symbol}: {e}")
                    else:
                        skipped.append((symbol, total))

                if passed:
                    logger.info(f"Cycle {cycle}: {len(passed)} signals sent: {[s[0] for s in passed]}")

                if verbose and new_pairs:
                    lines = [f"🔍 *Scan #{cycle}:* {len(new_pairs)} new tokens\n"]
                    for sym, sc in passed:
                        lines.append(f"  ✅ ${sym} — Score: {sc}")
                    for sym, sc in skipped[:10]:
                        lines.append(f"  ❌ ${sym} — Score: {sc}")
                    if len(skipped) > 10:
                        lines.append(f"  ... +{len(skipped) - 10} more skipped")
                    lines.append(f"\nPassed: {len(passed)} | Skipped: {len(skipped)}")
                    try:
                        await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)
                    except Exception as e:
                        logger.error(f"Verbose send error: {e}")
                elif cycle % 5 == 0 or passed:
                    heartbeat_emoji = "✅" if passed else "⏳"
                    lines = [f"{heartbeat_emoji} *Live Active* — Scan #{cycle}"]
                    if new_pairs:
                        lines.append(f"Scanned: {len(new_pairs)} tokens | Passed: {len(passed)} | Skipped: {len(skipped)}")
                    else:
                        lines.append("No new tokens found this cycle")
                    lines.append(f"Use `/live v` for detail, `/live` to stop")
                    try:
                        await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)
                    except Exception as e:
                        logger.error(f"Heartbeat send error: {e}")

                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info(f"Live loop cancelled for chat {chat_id}")

    _live_tasks[chat_id] = asyncio.create_task(live_loop())
    mode = "verbose" if verbose else "normal"
    return f"▶️ Live monitoring started ({mode}, interval 60s, 4 sources, min score >{MIN_SCORE_FOR_ALERT}).\nUse `/live v` for verbose mode. `/live` to stop."


async def cmd_pumpfun(chat_id: str, args: str) -> str:
    try:
        coins = await fetch_new_launches(limit=15)
    except Exception:
        return "❌ Gagal fetch data dari Pump.fun."

    if not coins:
        return "🔍 Tidak ada Pump.fun launches."

    lines = [f"🎭 *Pump.fun Scan* ({len(coins)} tokens)\n"]
    for coin in coins[:10]:
        twitter = "🐦" if coin.get("twitter") else ""
        telegram = "📢" if coin.get("telegram") else ""
        website = "🌐" if coin.get("website") else ""
        socials = " ".join(filter(None, [twitter, telegram, website])) or "-"
        lines.append(f"• *{coin['symbol']}* — {coin['name'][:20]} | {socials}")
        if coin.get("description"):
            desc = coin["description"][:60].replace("\n", " ")
            lines.append(f"  _{desc}_")

    return "\n".join(lines)


async def cmd_score(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /score <token_address>\nContoh: /score F6N6Q1kMRhNCcedX3RmUsMBTAi7vWm7Bh6oc4aonpump"

    token_address = args.strip().split()[0]
    try:
        info = await get_token_info(token_address)
    except Exception:
        return "❌ Gagal fetch data token."

    if not info:
        return f"❌ Token tidak ditemukan: `{token_address}`"

    analyzed = await analyze_token(info)
    return format_telegram_message(analyzed)


async def cmd_chats(chat_id: str, args: str) -> str:
    ids = get_active_chat_ids()
    if not ids:
        return "📋 Tidak ada chat terdaftar."

    lines = [f"📋 *Registered Chats* ({len(ids)})\n"]
    lines.append("Chat IDs:\n" + "\n".join(f"• `{c}`" for c in ids))
    lines.append("\nKirim /start untuk daftarkan chat ini")
    return "\n".join(lines)


async def cmd_help(chat_id: str, args: str) -> str:
    return (
        "🤖 *Meme Coin Scanner — Help*\n"
        "\n"
        "*Discovery:*\n"
        "/scan — Quick scan trending Solana meme coins\n"
        "/deepscan — Deep scan 50+ coins from 4 sources\n"
        "/filter <preset> — Custom filter (aggressive/balanced/conservative)\n"
        "/pumpfun — Scan Pump.fun token terbaru\n"
        "/score <addr> — Analisis token berdasarkan address\n"
        "/ai <addr> — AI analysis + charts\n"
        "/gem — Gem hunter: cari koin potensial naik ribuan %\n"
        "\n"
        "*Safety & Monitoring:*\n"
        "/live — Mulai/stop live monitoring\n"
        "/rughistory — Database riwayat rug deployer\n"
        "/rugcheck <addr> — Deteksi rug real-time\n"
        "/spikes — Cek volume spike terbaru\n"
        "/bundler <addr> — Deteksi aktivitas bundler/insider\n"
        "\n"
        "*AI Auto Signal:*\n"
        "/autoscan on/off — Aktifkan/matikan auto signal AI\n"
        "/autostatus — Status auto signal\n"
        "/signals — Riwayat sinyal 24 jam + reasoning\n"
        "\n"
        "*Watchlist:*\n"
        "/wl — Lihat token di watchlist\n"
        "/wladd <addr> — Tambah token ke watchlist\n"
        "/wlremove <addr> — Hapus dari watchlist\n"
        "\n"
        "*Whale Tracker:*\n"
        "/whales <addr> — Auto-detect whale wallets\n"
        "/whalefolio — Portfolio whale wallets\n"
        "/whaleadd <addr> — Tambah whale\n"
        "/whaleremove <addr> — Hapus whale\n"
        "\n"
        "*Deployer:*\n"
        "/deployer <addr> — Cek history creator\n"
        "/deployers — List deployer\n"
        "/deployeradd <addr> — Track deployer\n"
        "\n"
        "*Lainnya:*\n"
        "/export — Export scan CSV\n"
        "/chats — Chat terdaftar\n"
        "/help — Bantuan ini\n"
        "\n"
        "🤖 Auto signal broadcast tiap 5 menit"
    )


async def cmd_watchlist(chat_id: str, args: str) -> str:
    items = load_watchlist()
    if not items:
        return "📋 Watchlist kosong. Tambah dengan /wladd <address>"

    lines = [f"📋 *Watchlist* ({len(items)} tokens)\n"]
    for item in items[:10]:
        mc = item.get("current_mcap") or item.get("mcap_added", 0)
        ch = item.get("change_pct", 0)
        emoji = "📈" if ch > 0 else "📉" if ch < 0 else "➖"
        lines.append(f"{emoji} *{item.get('symbol', '?')}* — MCap: ${mc:,.0f}")
    return "\n".join(lines)


async def cmd_wl_add(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /wladd <token_address>"

    addr = args.strip().split()[0]
    try:
        info = await get_token_info(addr)
    except Exception:
        return "❌ Gagal fetch data token."

    if not info:
        return "❌ Token tidak ditemukan."

    bt = info.get("base_token", {})
    add_to_watchlist(addr, bt.get("symbol", "?"), bt.get("name", "?"), info.get("market_cap", 0), info.get("liquidity_usd", 0), info.get("url", ""))
    return f"✅ *{bt.get('symbol', '?')}* added to watchlist!\nMCap: ${info.get('market_cap', 0):,.0f} | Liq: ${info.get('liquidity_usd', 0):,.0f}"


async def cmd_wl_remove(chat_id: str, args: str) -> str:
    if not args:
        items = load_watchlist()
        if not items:
            return "📋 Watchlist kosong."
        lines = ["Kirim /wlremove <number>:\n"]
        for i, item in enumerate(items, 1):
            lines.append(f"[{i}] {item.get('symbol', '?')} ({item.get('address', '')[:12]}...)")
        return "\n".join(lines)

    arg = args.strip().split()[0]
    items = load_watchlist()

    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(items):
            remove_from_watchlist(items[idx]["address"])
            return f"✅ Removed {items[idx]['symbol']} from watchlist."
        return "❌ Invalid index."

    if remove_from_watchlist(arg):
        return "✅ Removed from watchlist."
    return "❌ Not found in watchlist."


async def cmd_export(chat_id: str, args: str) -> str:
    try:
        pairs = await fetch_trending_solana()
    except Exception:
        return "❌ Gagal fetch data."

    if not pairs:
        return "❌ No data to export."

    results = []
    for pair in pairs[:15]:
        liq = pair.get("liquidity_usd", 0)
        if liq < 3000:
            continue
        analyzed = await analyze_token(pair)
        s = analyzed["score"]
        results.append({
            "symbol": analyzed["symbol"], "name": analyzed["name"],
            "score": s["total_score"], "verdict": s["verdict"],
            "mcap": analyzed["market_cap"], "liq": analyzed["liquidity_usd"],
            "vol": analyzed["volume_24h"], "age": analyzed["age_minutes"],
        })

    path = export_csv(results)
    return f"✅ Exported {len(results)} tokens to:\n`{path}`"


async def cmd_filter(chat_id: str, args: str) -> str:
    from config import FILTER_PRESETS

    preset = args.strip().lower() if args else "balanced"
    p = FILTER_PRESETS.get(preset, FILTER_PRESETS.get("balanced", {}))

    if not p:
        keys = ", ".join(FILTER_PRESETS.keys())
        return f"Presets: {keys}\nUsage: /filter balanced"

    try:
        pairs = await fetch_trending_solana()
    except Exception:
        return "❌ Gagal fetch data."

    results = []
    for pair in pairs[:20]:
        liq = pair.get("liquidity_usd", 0)
        mcap = pair.get("market_cap", 0)
        age = pair.get("age_minutes", 0)

        if liq < p.get("liq_min", 0) or mcap > p.get("mcap_max", 0) or age > p.get("age_max", 999):
            continue

        analyzed = await analyze_token(pair)
        if analyzed["score"]["total_score"] >= p.get("score_min", 0):
            results.append(analyzed)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    if not results:
        return f"🔍 No tokens match filter: {p['name']}"

    lines = [f"🔍 *Filter: {p['name']}* ({len(results)} tokens)\n"]
    for r in results[:8]:
        s = r["score"]
        emoji = {"HOT": "🔥", "POTENTIAL": "🟢", "WATCH": "🟡", "CAUTION": "⬜"}.get(s["verdict"], "")
        line = f"{emoji} *{r['symbol']}* — {s['total_score']}/100 | ${r['market_cap']:,.0f} MCap | {r['age_minutes']:.0f}m"

        holders = s.get("details", {}).get("holders", {})
        top_holders = holders.get("top_holders", [])
        if top_holders:
            line += f"\n  👥 Top10: {holders.get('top10_concentration_pct', '?')}%"
            for j, h in enumerate(top_holders[:5], 1):
                addr = h.get("address", "?")
                pct = h.get("pct", 0)
                short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
                link = f"https://solscan.io/account/{addr}"
                whale = "🐋" if pct >= 5 else "🐬" if pct >= 2 else "🐟"
                line += f"\n    {j}. {whale} {pct:.1f}% — [{short}]({link})"

        lines.append(line)

    return "\n".join(lines)


async def cmd_whale_scan(chat_id: str, args: str) -> str:
    if args:
        from core.whale_detector import detect_whales_for_token
        token_addr = args.strip().split()[0]
        result = await detect_whales_for_token(token_addr, max_holders=30)

        if not result.get("found"):
            return f"❌ No holder data found for this token."

        risk = result.get("concentration_risk", "?")
        risk_emoji = {"low": "✅", "medium": "⚠️", "high": "🛑"}.get(risk, "❓")

        lines = [
            f"{risk_emoji} *Whale Analysis*\n",
            f"Token: `{token_addr}`\n",
            f"Total holders checked: {result['total_holders_checked']}\n",
            f"Whale supply: {result['total_whale_supply_pct']:.1f}% | Risk: *{risk.upper()}*\n",
            f"\n🐋 *WHALES* ({result['whale_count']})\n",
        ]
        for w in result.get("whales", [])[:5]:
            sol = f" | {w['sol_balance']:,.0f} SOL" if w.get("sol_balance") else ""
            lines.append(f"  {w['wallet_short']}: {w['supply_pct']:.1f}%{sol}")

        if result.get("dolphins"):
            lines.append(f"\n🐬 *DOLPHINS* ({result['dolphin_count']})\n")
            for d in result["dolphins"][:5]:
                lines.append(f"  {d['wallet_short']}: {d['supply_pct']:.1f}%")

        lines.append(f"\nUse /whales without args to scan tracked wallets")
        return "\n".join(lines)

    whales = load_known_whales()
    active_whales = [w for w in whales if "4hWp3n9k" not in w.get("address", "")]

    if not active_whales:
        return "🐋 No whale wallets configured.\nAdd with: /whaleadd <address> [name]"

    buys = await scan_whale_buys(min_volume_sol=0.01)
    if not buys:
        return f"🐋 Scanned {len(active_whales)} whales — no new buys detected.\nView portfolio: /whalefolio"

    lines = [f"🐋 *Whale Recent Buys* ({len(buys)})\n"]
    for b in buys[:10]:
        sym = b.get("token_symbol", b["token_mint"][:8])
        ts = datetime.fromtimestamp(b["time"], tz=timezone.utc).strftime("%H:%M") if b.get("time") else "?"
        lines.append(f"• *{b['wallet_name']}* -> {sym}: {b['amount_sol']:.3f} SOL ({ts})")

    lines.append(f"\nView full portfolio: /whalefolio")
    return "\n".join(lines)


async def cmd_whale_portfolio(chat_id: str, args: str) -> str:
    portfolios = await scan_whale_portfolios()
    if not portfolios:
        return "🐋 No whale portfolios found."

    text = ""
    for p in portfolios[:5]:
        text += f"\n🐋 *{p['name']}* — {p['total_tokens']} tokens\n"
        text += f"`{p['wallet'][:12]}...`\n"
        if p.get("holdings"):
            for h in p["holdings"][:5]:
                mint_short = str(h.get("mint", ""))[:10]
                text += f"  • {mint_short}... : {h.get('ui_amount', 0):,.2f}\n"
        else:
            text += "  No holdings\n"

    return text or "No data"


async def cmd_whale_add(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /whaleadd <wallet_address> [nickname]"

    parts = args.strip().split()
    addr = parts[0]
    name = " ".join(parts[1:]) if len(parts) > 1 else ""
    result = add_whale(addr, name)
    return f"🐋 Whale added: *{result['name']}*\n`{addr}`"


async def cmd_whale_remove(chat_id: str, args: str) -> str:
    if not args:
        whales = load_known_whales()
        if not whales:
            return "No whales tracked."
        lines = ["Kirim /whaleremove <number/address>:\n"]
        for i, w in enumerate(whales, 1):
            lines.append(f"[{i}] {w.get('name', '?')} ({w.get('address', '')[:12]}...)")
        return "\n".join(lines)

    arg = args.strip().split()[0]
    whales = load_known_whales()

    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(whales):
            remove_whale(whales[idx]["address"])
            return f"✅ Removed {whales[idx].get('name', 'whale')}."
        return "❌ Invalid index."

    if remove_whale(arg):
        return "✅ Whale removed."
    return "❌ Not found."


async def cmd_bundler(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /bundler <token_address>"

    addr = args.strip().split()[0]
    result = await detect_bundler_activity(addr)

    if not result.get("checked"):
        return f"❌ Cannot check bundler: {result.get('reason', 'unknown')}"

    if result["is_bundled"]:
        return (
            "🛑 *BUNDLER DETECTED!*\n"
            f"Token: `{addr}`\n"
            f"Rapid buys (<60s): {result['rapid_buys_under_60s']}\n"
            f"Unique buyers: {result['unique_buyers_first_5min']}\n"
            f"Risk: HIGH"
        )

    return (
        f"✅ *No Bundler Detected*\n"
        f"Unique buyers (5min): {result['unique_buyers_first_5min']}\n"
        f"Rapid buys: {result['rapid_buys_under_60s']}\n"
        f"Risk: {result.get('risk', 'low')}"
    )


async def cmd_smart_money(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /smartmoney <token_address>\nCek smart money & insider selling"

    addr = args.strip().split()[0]
    from core.dexscreener import get_token_info

    info = await get_token_info(addr)
    if not info:
        return f"❌ Token tidak ditemukan: {addr}"

    result = await analyze_token(info)
    sm = result.get("smart_money", {})
    if not sm.get("found"):
        return "❌ Smart money data unavailable (token terlalu tua atau tidak ada data on-chain)."

    risk_emoji = {"high": "🛑", "medium": "⚠️", "low": "✅", "unknown": "❓"}.get(sm.get("risk"), "❓")
    lines = [f"{risk_emoji} *Smart Money Analysis*\nToken: `{addr}`"]
    lines.append(f"Risk: *{sm.get('risk', '?').upper()}* | Signal: {sm.get('signal', '?')} | Score Adj: {sm.get('score_adjustment', 0)}")
    lines.append(f"Known smart holders: {sm.get('smart_holder_count', 0)}")
    if sm.get("early_buyer_retention_pct") is not None:
        lines.append(f"Early-buyer retention: {sm['early_buyer_retention_pct']}%")
    if sm.get("insider_selling"):
        lines.append("🚨 INSIDER SELLING DETECTED — early buyers cashing out")
    for h in sm.get("smart_holders", [])[:5]:
        lines.append(f"• {h['name']} ({h['wallet'][:12]}...) amt:{h['amount']:.2f} hits:{h.get('hit_count', 0)}")
    return "\n".join(lines)


async def cmd_narratives(chat_id: str, args: str) -> str:
    from core.dexscreener import fetch_trending_solana
    from core.narratives import classify_narrative, track_sector_momentum

    pairs = await fetch_trending_solana()
    if not pairs:
        return "🔍 Tidak ada token trending ditemukan."

    items = []
    for p in pairs[:20]:
        liq = p.get("liquidity_usd", 0)
        mcap = p.get("market_cap", 0)
        if liq < 3000 or mcap > 2000000:
            continue
        name = p.get("base_token", {}).get("name", "")
        sym = p.get("base_token", {}).get("symbol", "")
        pc = p.get("price_change")
        chg = pc.get("h24") if isinstance(pc, dict) else None
        items.append({
            "narratives": classify_narrative(name, sym),
            "volume_24h": p.get("volume_24h", 0),
            "price_change_24h": chg,
            "score": {"total_score": 0},
        })

    sectors = track_sector_momentum(items)
    if not sectors:
        return "📊 Tidak ada data sektor."

    lines = ["🧭 *Sector Momentum* (24h volume)\n"]
    for s in sectors[:10]:
        chg = s["avg_change_24h"]
        chg_str = f"+{chg:.1f}%" if chg > 0 else f"{chg:.1f}%"
        vold = s.get("volume_delta", 0)
        vold_str = f" (Δ${vold:,.0f})" if vold else ""
        lines.append(f"• *{s['narrative']}* — {s['token_count']} tok | Vol ${s['volume_24h']:,.0f}{vold_str} | {chg_str}")
    return "\n".join(lines)


async def cmd_spikes(chat_id: str, args: str) -> str:
    spikes = detect_spikes()
    if not spikes:
        history = load_history()
        return f"📊 No spikes detected.\nTracking {len(history)} tokens."

    lines = [f"📈 *Volume Spikes* ({len(spikes)})\n"]
    for s in spikes[:8]:
        lines.append(f"• *{s['symbol']}*: +{s['spike_pct']}% (${s['volume_now']:,.0f}) in {s['time_diff_minutes']}m")
    return "\n".join(lines)


async def cmd_deployer(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /deployer <token_address>\nCek history wallet creator token"

    addr = args.strip().split()[0]
    result = await analyze_token_deployer(addr)

    if not result.get("found"):
        return "❌ Could not determine creator wallet for this token."

    stats = result.get("stats", {})
    creator = result.get("creator", "?")
    status = stats.get("status", "unknown")
    rep_score = stats.get("reputation_score", 0)
    rep_emoji = {"TRUSTED": "✅", "RELIABLE": "🟢", "NEUTRAL": "🟡", "CAUTION": "🟠", "HIGH RISK": "🔴"}.get(status, "❓")

    return (
        f"{rep_emoji} *Deployer Check*\n"
        f"Creator: `{creator}`\n"
        f"Status: *{status}* | Reputation: *{rep_score}/100*\n"
        f"Tokens deployed: {stats.get('total_tokens_found', '?')}\n"
        f"Success rate: {stats.get('success_rate', 0):.0f}% | Rug: {stats.get('rug_count', 0)}\n"
        f"Last updated: {stats.get('last_updated', '?')[:10]}"
    )


async def cmd_deployers_list(chat_id: str, args: str) -> str:
    deployers = load_deployer_list()
    if not deployers:
        return "📋 No deployers tracked.\nAdd with: /deployeradd <address> [name]"

    lines = [f"📋 *Tracked Deployers* ({len(deployers)})\n"]
    for d in deployers[:10]:
        lines.append(f"• *{d.get('name', '?')}* — {d.get('address', '?')[:12]}... | Tokens: {d.get('total_deployed', '?')}")
    return "\n".join(lines)


async def cmd_deployer_add(chat_id: str, args: str) -> str:
    if not args:
        return "Usage: /deployeradd <wallet_address> [nickname]"

    parts = args.strip().split()
    addr = parts[0]
    name = " ".join(parts[1:]) if len(parts) > 1 else ""

    stats = await get_deployer_stats(addr)
    rep_score = stats.get("reputation_score", 0)
    result = add_deployer(addr, name)
    return (
        f"✅ Deployer added: *{result['name']}*\n"
        f"Reputation: {rep_score}/100 | "
        f"Success rate: {stats.get('success_rate', 0):.0f}% | "
        f"Rug: {stats.get('rug_count', 0)}"
    )


async def cmd_deepscan(chat_id: str, args: str) -> str:
    from core.deep_scanner import deep_scan

    try:
        pairs = await deep_scan(max_age_minutes=120, max_results=40)
    except Exception:
        return "❌ Gagal deep scan."

    if not pairs:
        return "🔍 No tokens found."

    results = []
    for pair in pairs[:40]:
        liq = pair.get("liquidity_usd", 0)
        mcap = pair.get("market_cap", 0)
        if mcap < 1000:
            continue

        dex = pair.get("dex", "")
        is_jup = "jupiter" in str(dex).lower()

        analyzed = await analyze_token(pair)

        score_total = analyzed["score"]["total_score"]
        if is_jup and (liq < 100 or score_total < 50):
            continue
        if liq < 500 and score_total < 50:
            continue

        results.append(analyzed)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    seen_symbols = {}
    unique_results = []
    for r in results:
        sym = r.get("symbol", "").upper()
        if sym in seen_symbols:
            continue
        seen_symbols[sym] = 1
        unique_results.append(r)

    results = unique_results[:12]

    if not results:
        return "🔍 No quality tokens found (min liq $3K, mcap $3K, score 40+).\nTry /scan for trending tokens."

    lines = [f"🔍 *Deep Scan* ({len(results)} tokens filtered)\n"]

    for i, r in enumerate(results):
        s = r["score"]
        pro = r.get("professional", {})
        sig = pro.get("signal", "BUY")
        sig_emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(sig, "❓")
        pc = r.get("price_change_24h", 0) or 0
        pc_str = f"📈{pc:+.0f}%" if pc >= 0 else f"📉{pc:.0f}%"
        age = r.get("age_minutes", 0) or 0
        age_str = f"{age:.0f}m" if age < 1440 else f"{age/60:.0f}h"
        safety_details = s.get("details", {}).get("safety", {})
        hp = safety_details.get("checks", {}).get("honeypot_detected", "?")
        hp_str = "✅" if hp is False else "🛑" if hp is True else "?"

        charts = r.get("charts", {})
        chart_link = charts.get("price_chart", "")

        line = f"{sig_emoji} {hp_str} *{r['symbol']}* — {s['total_score']}/100 | ${r['market_cap']:,.0f} | {pc_str} | {age_str}"
        if i < 3 and chart_link:
            line += f" | [Chart]({chart_link})"

        holders = s.get("details", {}).get("holders", {})
        top_holders = holders.get("top_holders", [])
        if i < 3 and top_holders:
            line += f"\n👥 Holders: {holders.get('total_holders', '?')} | Top10: {holders.get('top10_concentration_pct', '?')}%"
            for j, h in enumerate(top_holders[:5], 1):
                addr = h.get("address", "?")
                pct = h.get("pct", 0)
                short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
                link = f"https://solscan.io/account/{addr}"
                whale = "🐋" if pct >= 5 else "🐬" if pct >= 2 else "🐟"
                line += f"\n  {j}. {whale} {pct:.1f}% — [{short}]({link})"

        lines.append(line)

    return "\n".join(lines)


async def cmd_autoscan(chat_id: str, args: str) -> str:
    from core.auto_signal import set_auto_running, is_auto_running

    cmd = args.strip().lower() if args else "status"
    if cmd == "on":
        set_auto_running(True)
        return "✅ Auto signal broadcaster *AKTIF*\nScan 30+ tokens tiap 5 menit, kirim sinyal ke semua chat."
    elif cmd == "off":
        set_auto_running(False)
        return "⏸️ Auto signal broadcaster *MATI*"
    else:
        status = "AKTIF" if is_auto_running() else "MATI"
        return f"Auto scan status: *{status}*\nGunakan /autoscan on atau /autoscan off"


async def cmd_autostatus(chat_id: str, args: str) -> str:
    from core.auto_signal import is_auto_running, get_recent_signals

    running = is_auto_running()
    sigs = get_recent_signals(24)

    status_text = "AKTIF" if running else "MATI"
    text = f"🤖 *Auto Signal Status*\n"
    text += f"Status: *{status_text}*\n"
    text += f"Interval: 5 menit\n"
    text += f"Min score: 70\n"
    text += f"Signals (24h): {len(sigs)}\n"

    if sigs:
        text += f"\n*Recent signals:*\n"
        for s in sigs[:5]:
            emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(s.get("signal", ""), "❓")
            ts = datetime.fromtimestamp(s.get("timestamp", 0), tz=timezone.utc).strftime("%m/%d %H:%M")
            text += f"{emoji} {s['symbol']} ({s['signal']}) — {s.get('mcap', 0):,.0f} | {ts}\n"

    return text


async def cmd_signals(chat_id: str, args: str) -> str:
    from core.auto_signal import get_recent_signals

    sigs = get_recent_signals(24)
    if not sigs:
        return "📋 No signals in last 24 hours."

    text = f"📋 *Recent Signals* ({len(sigs)})\n"
    for s in sigs[:15]:
        emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(s.get("signal", ""), "❓")
        ts = datetime.fromtimestamp(s.get("timestamp", 0), tz=timezone.utc).strftime("%H:%M")
        reasoning = s.get("reasoning", "")[:80] if s.get("reasoning") else ""
        text += f"{emoji} *{s['symbol']}* | {s['signal']} | {ts}\n"
        if reasoning:
            text += f"  _{reasoning}_\n"

    return text


async def cmd_ai_analysis(chat_id: str, args: str) -> str:
    from core.ai_analyzer import analyze_with_ai
    from alerts.charts import generate_charts_for_token

    if not args:
        return "Usage: /ai <token_address>\nAnalisis token dengan AI + charts"

    token_address = args.strip().split()[0]

    try:
        info = await get_token_info(token_address)
    except Exception:
        return "Gagal fetch data token."

    if not info:
        return f"Token tidak ditemukan: `{token_address}`"

    analyzed = await analyze_token(info)

    if not analyzed.get("charts"):
        analyzed["charts"] = generate_charts_for_token(analyzed)

    ai_result = await analyze_with_ai(analyzed)
    analyzed["ai_analysis"] = ai_result

    signal = ai_result.get("signal", "WATCH")
    confidence = ai_result.get("confidence", "?")
    reasoning = ai_result.get("reasoning", "")
    target = ai_result.get("target_price_pct", "N/A")
    stop_loss = ai_result.get("stop_loss_pct", "N/A")
    risk = ai_result.get("risk_level", "?")
    position = ai_result.get("position_size", "N/A")
    strengths = ai_result.get("key_strengths", [])
    risks_list = ai_result.get("key_risks", [])
    source = ai_result.get("source", "ai")

    sig_emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(signal, "❓")
    source_label = "AI" if source == "ai" else "Engine"

    score = analyzed.get("score", {})
    total = score.get("total_score", 0)
    mcap = analyzed.get("market_cap", 0)
    liq = analyzed.get("liquidity_usd", 0)
    price = analyzed.get("price_usd", 0)
    price_ch = analyzed.get("price_change_24h", 0) or 0
    age = analyzed.get("age_minutes", "?")
    symbol = analyzed.get("symbol", "???")
    name = analyzed.get("name", "Unknown")

    holders = score.get("details", {}).get("holders", {})
    safety = score.get("details", {}).get("safety", {})
    checks = safety.get("checks", {})
    onchain = analyzed.get("onchain_metrics", {})
    social_sent = analyzed.get("social_sentiment", {})

    hp = checks.get("honeypot_detected", "?")
    hp_text = "YES" if hp is True else "No"
    deployer = analyzed.get("deployer_check", {}).get("stats", {})
    dep_status = deployer.get("status", "unknown")
    whale = analyzed.get("auto_whales", {})
    whale_pct = whale.get("total_whale_supply_pct", 0)

    pc_emoji = "+" if price_ch > 0 else ""
    age_str = f"{age:.0f}m" if isinstance(age, (int, float)) else str(age)

    momentum = onchain.get("momentum", "unknown")
    momentum_emoji = {"surging": "🚀", "rising": "📈", "stable": "➡️", "declining": "📉"}.get(momentum, "❓")
    buyers = onchain.get("unique_buyers_1h", 0)
    sellers = onchain.get("unique_sellers_1h", 0)
    ratio = onchain.get("buyer_seller_ratio", 0)
    data_quality = ai_result.get("data_quality", 0)

    social_str = ""
    if social_sent.get("has_twitter"):
        social_str += "🐦"
    if social_sent.get("has_telegram"):
        social_str += "📢"
    if social_sent.get("has_website"):
        social_str += "🌐"
    if not social_str:
        social_str = "None"

    msg = (
        f"{sig_emoji} *{source_label}: ${symbol}*\n"
        f"*{name}*\n"
        f"{'─' * 25}\n"
        f"*AI Analysis:*\n"
        f"_{reasoning}_\n"
        f"{'─' * 25}\n"
        f"Score: {total}/100 | Confidence: {confidence}/10 | Data: {data_quality}%\n"
        f"MCap: ${mcap:,.0f} | Liq: ${liq:,.0f}\n"
        f"Price: ${price:.8f} | {pc_emoji}{price_ch:.0f}%\n"
        f"Honeypot: {hp_text} | Deployer: {dep_status}\n"
        f"Holders: {holders.get('total_holders', '?')} (top10: {holders.get('top10_concentration_pct', '?')}%)\n"
        f"Whale supply: {whale_pct:.1f}%\n"
        f"{momentum_emoji} Momentum: {momentum} | Buy/Sell: {buyers}/{sellers} ({ratio}x)\n"
        f"Social: {social_str}\n"
        f"Target: {target} | Stop: {stop_loss}\n"
        f"Risk: {risk} | Position: {position}\n"
    )

    if strengths:
        msg += f"Strengths: {', '.join(strengths[:3])}\n"
    if risks_list:
        msg += f"Risks: {', '.join(risks_list[:3])}\n"

    charts = analyzed.get("charts", {})
    msg += _format_top_holders(holders)
    msg += f"\nAge: {age_str}"
    if charts.get("price_chart"):
        msg += f" | [Price Chart]({charts['price_chart']})"
    if charts.get("score_chart"):
        msg += f" | [Score]({charts['score_chart']})"
    if analyzed.get("url"):
        msg += f"\n[DexScreener]({analyzed['url']})"

    return msg


async def cmd_gem_hunter(chat_id: str, args: str) -> str:
    from core.deep_scanner import deep_scan
    from core.ai_analyzer import analyze_with_ai
    from alerts.charts import generate_charts_for_token

    try:
        pairs = await deep_scan(max_age_minutes=60, max_results=50)
    except Exception:
        return "Gagal scan."

    if not pairs:
        return "Tidak ada token ditemukan."

    gems = []
    for pair in pairs:
        mcap = pair.get("market_cap", 0)
        liq = pair.get("liquidity_usd", 0)
        vol = pair.get("volume_24h", 0)
        age = pair.get("age_minutes", 0)

        if mcap < 500 or mcap > 100000:
            continue
        if liq < 1000:
            continue
        if age > 60 and age > 0:
            continue

        analyzed = await analyze_token(pair)

        score = analyzed["score"]["total_score"]
        pro = analyzed.get("professional", {})
        sig = pro.get("signal", "WATCH")
        safety = analyzed["score"]["details"].get("safety", {})
        checks = safety.get("checks", {})
        hp = checks.get("honeypot_detected", False)
        deployer = analyzed.get("deployer_check", {}).get("stats", {})
        dep_status = deployer.get("status", "unknown")

        if hp is True:
            continue
        if dep_status == "suspicious":
            continue
        if score < 50:
            continue

        vol_mcap_ratio = vol / mcap if mcap > 0 else 0
        if vol_mcap_ratio < 0.1:
            continue

        analyzed["gem_score"] = _calculate_gem_score(analyzed, vol_mcap_ratio)
        gems.append(analyzed)

    gems.sort(key=lambda x: x.get("gem_score", 0), reverse=True)
    gems = gems[:8]

    if not gems:
        return "Tidak ada gem ditemukan saat ini. Coba lagi nanti."

    lines = ["*GEM HUNTER Results*\n"]
    lines.append("Kriteria: MCap <$100K, Age <60m, Safety >50, No honeypot, Vol/MCap >0.1\n")

    for i, g in enumerate(gems):
        gem_score = g.get("gem_score", 0)
        pro = g.get("professional", {})
        sig = pro.get("signal", "WATCH")
        sig_emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(sig, "❓")
        pc = g.get("price_change_24h", 0) or 0
        pc_str = f"+{pc:.0f}%" if pc >= 0 else f"{pc:.0f}%"
        age = g.get("age_minutes", 0) or 0
        age_str = f"{age:.0f}m" if age < 1440 else f"{age/60:.0f}h"
        mcap = g.get("market_cap", 0)
        vol = g.get("volume_24h", 0)
        liq = g.get("liquidity_usd", 0)
        holders = g["score"]["details"].get("holders", {}).get("total_holders", "?")
        deployer = g.get("deployer_check", {}).get("stats", {})
        dep = deployer.get("status", "?")
        checks = g["score"]["details"].get("safety", {}).get("checks", {})
        hp = checks.get("honeypot_detected", "?")
        hp_str = "OK" if hp is False else "!" if hp is True else "?"

        charts = g.get("charts", {})
        chart_link = charts.get("price_chart", "")

        line = f"{sig_emoji} *{g['symbol']}* | Gem: {gem_score}/100 | {g['score']['total_score']}/100\n"
        line += f"  MCap: ${mcap:,.0f} | Liq: ${liq:,.0f} | Vol: ${vol:,.0f}\n"
        line += f"  24h: {pc_str} | Age: {age_str} | Holders: {holders} | Dep: {dep}\n"
        line += f"  HP: {hp_str}"
        if chart_link:
            line += f" | [Chart]({chart_link})"
        if g.get("url"):
            line += f" | [DexScreener]({g['url']})"

        holders_data = g["score"]["details"].get("holders", {})
        top_holders = holders_data.get("top_holders", [])
        if top_holders:
            line += f"\n  👥 Top Wallets:"
            for j, h in enumerate(top_holders[:5], 1):
                addr = h.get("address", "?")
                pct = h.get("pct", 0)
                short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
                link = f"https://solscan.io/account/{addr}"
                whale = "🐋" if pct >= 5 else "🐬" if pct >= 2 else "🐟"
                line += f"\n    {j}. {whale} {pct:.1f}% — [{short}]({link})"

        lines.append(line)

    return "\n".join(lines)


def _calculate_gem_score(result: Dict, vol_mcap_ratio: float) -> int:
    score = 0

    mcap = result.get("market_cap", 0)
    if mcap < 10000:
        score += 25
    elif mcap < 30000:
        score += 20
    elif mcap < 50000:
        score += 15
    else:
        score += 5

    age = result.get("age_minutes", 999)
    if age < 5:
        score += 20
    elif age < 15:
        score += 15
    elif age < 30:
        score += 10
    else:
        score += 5

    safety = result["score"]["details"].get("safety", {}).get("score", 0)
    if safety >= 90:
        score += 20
    elif safety >= 70:
        score += 15
    elif safety >= 50:
        score += 10

    if vol_mcap_ratio >= 2:
        score += 15
    elif vol_mcap_ratio >= 1:
        score += 10
    elif vol_mcap_ratio >= 0.5:
        score += 5

    deployer = result.get("deployer_check", {}).get("stats", {})
    dep_status = deployer.get("status", "unknown")
    dep_rep = deployer.get("reputation_score", 0)
    if dep_status in ("TRUSTED", "RELIABLE") or dep_rep >= 60:
        score += 10
    elif dep_rep >= 40:
        score += 5

    holders = result["score"]["details"].get("holders", {}).get("total_holders", 0)
    if isinstance(holders, (int, float)) and holders >= 50:
        score += 10
    elif isinstance(holders, (int, float)) and holders >= 20:
        score += 5

    return min(100, score)


async def cmd_wallet(chat_id: str, args: str) -> str:
    from core.wallet_manager import link_wallet, unlink_wallet, get_wallet_balance, get_wallet

    if not args:
        wallet = get_wallet(chat_id)
        if not wallet:
            return "Wallet belum tertaut.\nGunakan: /wallet link <private_key>"

        balance = await get_wallet_balance(chat_id)
        if balance:
            return (
                f"*Wallet Info*\n"
                f"Address: `{balance['address']}`\n"
                f"SOL: {balance['sol_balance']}\n"
                f"Tokens: {balance['token_count']}\n"
                f"Auto Trade: {'ON' if wallet.get('auto_trade_enabled') else 'OFF'}\n"
                f"Mode: {wallet.get('trade_mode', 'full-auto')}\n"
                f"Buy Amount: {wallet.get('buy_amount_sol', 0.1)} SOL\n"
                f"Max Positions: {wallet.get('max_positions', 5)}"
            )
        return f"Wallet: `{wallet['wallet_address']}`"

    parts = args.strip().split(maxsplit=1)
    action = parts[0].lower()

    if action == "link":
        if len(parts) < 2:
            return "Gunakan: /wallet link <private_key>\nPrivate key dalam format hex atau base64"
        private_key = parts[1].strip()
        result = link_wallet(chat_id, private_key)
        if result["success"]:
            balance = await get_wallet_balance(chat_id)
            sol = balance.get("sol_balance", 0) if balance else 0
            return (
                f"Wallet tertaut!\n"
                f"Address: `{result['address']}`\n"
                f"SOL: {sol}\n"
                f"Gunakan /autotrade on untuk aktifkan auto trade"
            )
        return f"Gagal: {result.get('error', 'Unknown error')}\n\nFormat private key yang didukung:\n- Hex (64 karakter)\n- Base64\n- Base58 (dari Phantom/Solflare)\n- JSON array [123,45,...]"

    elif action == "unlink":
        if unlink_wallet(chat_id):
            return "Wallet dihapus dari bot."
        return "Tidak ada wallet tertaut."

    return "Gunakan: /wallet, /wallet link <key>, atau /wallet unlink"


async def cmd_autotrade(chat_id: str, args: str) -> str:
    from core.wallet_manager import get_wallet, update_wallet_config

    wallet = get_wallet(chat_id)
    if not wallet:
        return "Wallet belum tertaut. Gunakan /wallet link <private_key>"

    if not args:
        mode = wallet.get("trade_mode", "full-auto")
        enabled = wallet.get("auto_trade_enabled", False)
        return (
            f"*Auto Trade Status*\n"
            f"Status: {'ON' if enabled else 'OFF'}\n"
            f"Mode: {mode}\n"
            f"Buy Amount: {wallet.get('buy_amount_sol', 0.1)} SOL\n"
            f"Stop Loss: {wallet.get('stop_loss_pct', -40)}%\n"
            f"Take Profit: +{wallet.get('take_profit_pct', 100)}%\n"
            f"Max Positions: {wallet.get('max_positions', 5)}\n"
            f"\nCommands:\n"
            f"/autotrade on - Aktifkan\n"
            f"/autotrade off - Matikan\n"
            f"/autotrade amount <sol> - Set buy amount\n"
            f"/autotrade sl <persen> - Set stop loss\n"
            f"/autotrade tp <persen> - Set take profit"
        )

    parts = args.strip().split()
    action = parts[0].lower()

    if action == "on":
        update_wallet_config(chat_id, {"auto_trade_enabled": True})
        return "Auto trade AKTIF - Mode: FULL AUTO\nBot akan otomatis buy saat AI signal BUY (confidence >7)"

    elif action == "off":
        update_wallet_config(chat_id, {"auto_trade_enabled": False})
        return "Auto trade MATI"

    elif action == "amount" and len(parts) > 1:
        try:
            amount = float(parts[1])
            if amount <= 0 or amount > 10:
                return "Amount harus antara 0.01 - 10 SOL"
            update_wallet_config(chat_id, {"buy_amount_sol": amount})
            return f"Buy amount: {amount} SOL"
        except ValueError:
            return "Format: /autotrade amount 0.1"

    elif action == "sl" and len(parts) > 1:
        try:
            sl = float(parts[1])
            if sl > 0:
                sl = -sl
            if sl < -90 or sl > 0:
                return "Stop loss harus antara -1% sampai -90%"
            update_wallet_config(chat_id, {"stop_loss_pct": sl})
            return f"Stop loss: {sl}%"
        except ValueError:
            return "Format: /autotrade sl 40"

    elif action == "tp" and len(parts) > 1:
        try:
            tp = float(parts[1])
            if tp < 10 or tp > 10000:
                return "Take profit harus antara 10% - 10000%"
            update_wallet_config(chat_id, {"take_profit_pct": tp})
            return f"Take profit: +{tp}%"
        except ValueError:
            return "Format: /autotrade tp 100"

    return "Gunakan: /autotrade on/off/amount/sl/tp"


async def cmd_buy(chat_id: str, args: str) -> str:
    from core.trade_executor import execute_buy
    from core.wallet_manager import get_wallet
    from core.dexscreener import get_token_info

    if not args:
        return "Gunakan: /buy <token_address> [amount_sol]\nContoh: /buy BqkHUT... 0.1"

    parts = args.strip().split()
    token_address = parts[0]
    wallet = get_wallet(chat_id)

    if not wallet:
        return "Wallet belum tertaut. Gunakan /wallet link <private_key>"

    amount = wallet.get("buy_amount_sol", 0.1)
    if len(parts) > 1:
        try:
            amount = float(parts[1])
        except ValueError:
            return "Format: /buy <token_address> <amount_sol>"

    info = await get_token_info(token_address)
    if not info:
        return f"Token tidak ditemukan: `{token_address}`"

    symbol = info.get("base_token", {}).get("symbol", "?")
    price = info.get("price_usd", 0)

    result = await execute_buy(chat_id, token_address, symbol, amount, price)

    if result["success"]:
        return (
            f"BUY SUCCESS!\n"
            f"Token: {symbol}\n"
            f"Amount: {amount} SOL\n"
            f"Tx: `{result.get('tx_hash', '?')[:16]}...`\n"
            f"Target: +{wallet.get('take_profit_pct', 100)}% | Stop: {wallet.get('stop_loss_pct', -40)}%\n"
            f"Gunakan /positions untuk cek posisi"
        )
    return f"Buy gagal: {result.get('error', 'Unknown error')}"


async def cmd_sell(chat_id: str, args: str) -> str:
    from core.trade_executor import execute_sell
    from core.position_tracker import get_open_positions

    if not args:
        positions = get_open_positions(chat_id)
        if not positions:
            return "Tidak ada posisi terbuka."
        lines = ["*Open Positions:*\n"]
        for i, p in enumerate(positions, 1):
            pnl = p.get("pnl_pct", 0)
            emoji = "+" if pnl >= 0 else ""
            lines.append(f"[{i}] {p['symbol']} | {emoji}{pnl:.0f}% | {p['amount_sol']} SOL")
        lines.append("\nGunakan: /sell <token_address> atau /sell all")
        return "\n".join(lines)

    if args.strip().lower() == "all":
        positions = get_open_positions(chat_id)
        if not positions:
            return "Tidak ada posisi."
        results = []
        for p in positions:
            r = await execute_sell(chat_id, p["token_address"], 1.0)
            results.append(f"{p['symbol']}: {'OK' if r['success'] else 'FAIL'}")
        return "Sell all:\n" + "\n".join(results)

    result = await execute_sell(chat_id, args.strip(), 1.0)
    if result["success"]:
        pos = result.get("position", {})
        pnl = pos.get("pnl_pct", 0)
        emoji = "+" if pnl >= 0 else ""
        return (
            f"SELL SUCCESS!\n"
            f"Token: {pos.get('symbol', '?')}\n"
            f"P&L: {emoji}{pnl:.0f}% ({emoji}{pos.get('pnl_sol', 0):.4f} SOL)\n"
            f"Tx: `{result.get('tx_hash', '?')[:16]}...`"
        )
    return f"Sell gagal: {result.get('error', 'Unknown error')}"


async def cmd_positions(chat_id: str, args: str) -> str:
    from core.position_tracker import get_open_positions, get_trade_stats

    positions = get_open_positions(chat_id)
    stats = get_trade_stats(chat_id)

    text = f"*Position Tracker*\n"
    text += f"Open: {stats['open_positions']} | Win Rate: {stats['win_rate']}%\n"
    text += f"Total P&L: {'+' if stats['total_pnl_sol'] >= 0 else ''}{stats['total_pnl_sol']:.4f} SOL\n"
    text += f"{'─' * 25}\n"

    if not positions:
        text += "Tidak ada posisi terbuka.\n"
        text += "Gunakan /buy <token> atau aktifkan /autotrade on"
        return text

    for p in positions:
        pnl = p.get("pnl_pct", 0)
        emoji = "🟢" if pnl >= 20 else "🟡" if pnl >= 0 else "🔴"
        pnl_emoji = "+" if pnl >= 0 else ""
        text += f"{emoji} *{p['symbol']}* | {pnl_emoji}{pnl:.0f}% | {p['amount_sol']} SOL\n"

    return text


async def cmd_rugcheck(chat_id: str, args: str) -> str:
    from core.rug_monitor import check_rug_indicators
    from core.dexscreener import get_token_info

    if not args:
        return "Gunakan: /rugcheck <token_address>"

    token_address = args.strip()
    info = await get_token_info(token_address)
    if not info:
        return f"Token tidak ditemukan: `{token_address}`"

    price = info.get("price_usd", 0)
    liq = info.get("liquidity_usd", 0)

    rug = await check_rug_indicators(token_address, price, liq)

    symbol = info.get("base_token", {}).get("symbol", "?")

    if rug["is_rug"]:
        triggers = "\n".join([f"⛔ {t}" for t in rug["triggers"]])
        return (
            f"🚨 *RUG DETECTED: ${symbol}*\n"
            f"{triggers}\n"
            f"Price: {rug['price_change_pct']:.0f}%\n"
            f"LP: {rug['lp_change_pct']:.0f}%"
        )

    return (
        f"✅ *${symbol} - No Rug Detected*\n"
        f"Price: {rug['price_change_pct']:.0f}%\n"
        f"LP: {rug['lp_change_pct']:.0f}%\n"
        f"Triggers: None"
    )


async def cmd_rughistory(chat_id: str, args: str) -> str:
    from core.rug_history import get_rug_stats, get_rug_events, check_deployer_rug_history

    if args:
        deployer = args.strip()
        hist = check_deployer_rug_history(deployer)
        if not hist.get("has_rug_history"):
            return f"✅ Deployer `{deployer[:12]}...` tidak memiliki riwayat rug."
        lines = [f"🛑 *Deployer Rug History*\n`{deployer[:12]}...`\n"]
        lines.append(f"Total rugs: *{hist['total_rugs']}*")
        lines.append(f"Last rug: {hist.get('last_rug', '?')[:10]}\n")
        for e in hist.get("events", [])[:10]:
            lines.append(f"• {e.get('detected_at', '?')[:10]} — ${e.get('token_symbol', '?')} "
                         f"({e.get('reason', '?')})")
        return "\n".join(lines)

    stats = get_rug_stats(30)
    events = get_rug_events(20)

    lines = [f"📊 *Rug History Database*\n"]
    lines.append(f"Total events: {stats['total_rugs']}")
    lines.append(f"Unique deployers: {stats['unique_deployers']}")
    lines.append(f"Last 30 days: {stats.get('rugs_last_30d', 0)}")

    if stats["top_deployers"]:
        lines.append(f"\n🔴 *Top Rug Deployers:*")
        for d in stats["top_deployers"][:5]:
            lines.append(f"  • `{d['address'][:12]}...` — {d['total_rugs']}x rugs (last: {d['last_rug']})")

    if events:
        lines.append(f"\n📋 *Recent Events:*")
        for e in events[:10]:
            lines.append(f"  • {e.get('detected_at', '?')[:10]} — ${e.get('token_symbol', '?')} "
                         f"| drop: {e.get('price_drop_pct', 0):.0f}% | {e.get('reason', '?')}")

    lines.append(f"\nGunakan /rughistory <deployer_address> untuk cek spesifik.")
    return "\n".join(lines)


async def cmd_compare(chat_id: str, args: str) -> str:
    from core.token_comparator import compare_tokens

    if not args:
        return "Gunakan: /compare <addr1> <addr2>"

    parts = args.strip().split()
    if len(parts) < 2:
        return "Perlu 2 token address: /compare <addr1> <addr2>"

    result = await compare_tokens(parts[0], parts[1])
    if result.get("error"):
        return result["error"]

    tokens = result["tokens"]
    if len(tokens) < 2:
        return "Salah satu token tidak ditemukan."

    t1, t2 = tokens
    winner = result.get("winner_symbol", "Tie")
    winner_emoji = "🏆" if result.get("winner") != "tie" else "🤝"

    return (
        f"*Token Comparison*\n"
        f"{'─' * 20}\n"
        f"*1. ${t1['symbol']}*\n"
        f"  MCap: ${t1['market_cap']:,.0f} | Liq: ${t1['liquidity_usd']:,.0f}\n"
        f"  Volume: ${t1['volume_24h']:,.0f} | Age: {t1['age_minutes']:.0f}m\n"
        f"\n"
        f"*2. ${t2['symbol']}*\n"
        f"  MCap: ${t2['market_cap']:,.0f} | Liq: ${t2['liquidity_usd']:,.0f}\n"
        f"  Volume: ${t2['volume_24h']:,.0f} | Age: {t2['age_minutes']:.0f}m\n"
        f"\n"
        f"{winner_emoji} *Winner: ${winner}*\n"
        f"Scores: {t1['symbol']} {result['comparison'].get('scores', {}).get('token1', 0)} - "
        f"{result['comparison'].get('scores', {}).get('token2', 0)} {t2['symbol']}"
    )


async def cmd_verify_token(chat_id: str, args: str) -> str:
    from core.contract_verifier import verify_contract_safety, detect_whale_clusters
    from core.dexscreener import get_token_info
    from core.whale_detector import detect_whales_for_token

    if not args:
        return "Gunakan: /verify <token_address>"

    token_address = args.strip().split()[0]
    info = await get_token_info(token_address)
    if not info:
        return f"Token tidak ditemukan."

    symbol = info.get("base_token", {}).get("symbol", "?")

    safety = await verify_contract_safety(token_address)

    whales = await detect_whales_for_token(token_address, max_holders=30)
    clusters = await detect_whale_clusters(token_address, whales.get("whales", []) if whales else [])

    mint_ok = "✅" if safety["mint_renounced"] else "❌"
    freeze_ok = "✅" if safety["freeze_disabled"] else "❌"
    lp_ok = "✅" if safety["lp_burned"] else "❌"

    return (
        f"*Contract Verification: ${symbol}*\n"
        f"{'─' * 25}\n"
        f"Mint Renounced: {mint_ok}\n"
        f"Freeze Disabled: {freeze_ok}\n"
        f"LP Burned: {lp_ok}\n"
        f"Safety Score: {safety['score']}/85\n"
        f"Risk Level: *{safety['risk_level'].upper()}*\n"
        f"\n"
        f"*Whale Clustering:*\n"
        f"Clusters: {clusters['cluster_count']} (risk: {clusters['risk']})\n"
        + ("".join([f"  Funder: {c['funder']} ({c['wallet_count']} wallets)\n" for c in clusters.get("clusters", [])[:3]]))
        + f"\n"
        f"*Risks:*\n"
        + ("".join([f"  ⚠️ {r}\n" for r in safety['risks'][:3]]))
    )


async def cmd_report(chat_id: str, args: str) -> str:
    from core.position_tracker import get_open_positions, get_trade_stats
    from core.wallet_manager import get_wallet, get_wallet_balance

    stats = get_trade_stats(chat_id)
    positions = get_open_positions(chat_id)
    wallet = get_wallet(chat_id)

    text = f"*Trading Report*\n"
    text += f"{'─' * 20}\n"

    if wallet:
        balance = await get_wallet_balance(chat_id)
        text += f"*Wallet:*\n"
        text += f"  Address: `{balance['address'][:12]}...`\n" if balance else ""
        text += f"  SOL: {balance['sol_balance']}\n" if balance and balance.get('sol_balance') else ""
        text += f"  Auto Trade: {'ON' if wallet.get('auto_trade_enabled') else 'OFF'}\n"
        text += f"\n"

    text += f"*Stats:*\n"
    text += f"  Total Trades: {stats['total_trades']}\n"
    text += f"  Win Rate: {stats['win_rate']}%\n"
    text += f"  Wins: {stats['wins']} | Losses: {stats['losses']}\n"
    text += f"  Open Positions: {stats['open_positions']}\n"
    text += f"  Total P&L: {'+' if stats['total_pnl_sol'] >= 0 else ''}{stats['total_pnl_sol']:.4f} SOL\n"

    if positions:
        text += f"\n*Open:*\n"
        for p in positions[:5]:
            pnl = p.get("pnl_pct", 0)
            emoji = "🟢" if pnl >= 20 else "🟡" if pnl >= 0 else "🔴"
            text += f"  {emoji} {p['symbol']}: {'+' if pnl>=0 else ''}{pnl:.0f}% | {p['amount_sol']} SOL\n"

    text += f"\n/signals untuk riwayat sinyal | /positions untuk detail"
    return text


async def cmd_sell_mode(chat_id: str, args: str) -> str:
    from core.advanced_trader import load_trade_config, save_trade_config

    config = load_trade_config(chat_id)

    if not args:
        psl = config.get("partial_sell_enabled", False)
        tsl = config.get("trailing_stop_enabled", False)
        dba = config.get("dynamic_buy_enabled", False)

        return (
            f"*Advanced Trade Settings*\n"
            f"{'─' * 20}\n"
            f"Partial Sell: {'ON' if psl else 'OFF'}\n"
            f"  Levels: 25% @ +50%, 25% @ +100%, 50% @ +200%\n"
            f"Trailing Stop: {'ON' if tsl else 'OFF'}\n"
            f"  Start: +{config.get('trailing_stop_start', 50)}%, Distance: {config.get('trailing_stop_distance', 20)}%\n"
            f"Dynamic Buy: {'ON' if dba else 'OFF'}\n"
            f"  Conf 10: {config['dynamic_buy_amounts'].get('10', 0.3)} SOL | Conf 7: {config['dynamic_buy_amounts'].get('7', 0.1)} SOL\n"
            f"\n/sellmode partial on/off"
            f"\n/sellmode trailing on/off"
            f"\n/sellmode dynamic on/off"
        )

    parts = args.strip().split()
    if len(parts) < 2:
        return "Gunakan: /sellmode <feature> on/off"

    feature = parts[0].lower()
    action = parts[1].lower()

    if action not in ("on", "off"):
        return "Gunakan on atau off"

    enabled = action == "on"

    if feature == "partial":
        config["partial_sell_enabled"] = enabled
    elif feature == "trailing":
        config["trailing_stop_enabled"] = enabled
    elif feature == "dynamic":
        config["dynamic_buy_enabled"] = enabled
    else:
        return "Feature: partial, trailing, atau dynamic"

    save_trade_config(chat_id, config)
    return f"{feature} {'ON' if enabled else 'OFF'}"


async def cmd_performance(chat_id: str, args: str) -> str:
    from core.feedback_tracker import get_performance_stats
    from core.market_context import get_market_context, get_market_summary

    stats = get_performance_stats()
    market = await get_market_context()
    market_str = get_market_summary(market)

    text = f"*Performance & Market*\n"
    text += f"{'─' * 20}\n"
    text += f"{market_str}\n\n"

    if stats["closed_signals"] == 0:
        text += f"Total Signals: {stats['total_signals']}\n"
        text += f"Closed: 0 (menunggu 24h untuk evaluasi)\n"
        text += f"\nPerforma akan terlihat setelah signal berusia >24 jam."
        return text

    text += f"*Signal Stats:*\n"
    text += f"Total: {stats['total_signals']} | Closed: {stats['closed_signals']}\n"
    text += f"Win: {stats['wins']} | Loss: {stats['losses']} | Neutral: {stats['neutral']}\n"
    text += f"Win Rate: {stats['win_rate']}%\n"
    text += f"Avg Win: +{stats['avg_win_pct']}% | Avg Loss: {stats['avg_loss_pct']}%\n"
    text += f"Best Confidence: {stats['best_confidence']}/10\n"

    recent = stats.get("recent_signals", [])
    if recent:
        text += f"\n*Recent:*\n"
        for s in recent[:5]:
            outcome = s.get("outcome", "open")
            emoji = {"win": "+", "loss": "-", "open": "~", "neutral": "="}.get(outcome, "?")
            text += f"  {emoji} {s['symbol']}: {s['signal']} ({s['confidence']}/10) → {outcome}\n"

    return text
