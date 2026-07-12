import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Set

from utils.telegram_client import create_bot

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MIN_SCORE_FOR_ALERT

logger = logging.getLogger("memecoin-bot")

CHATS_FILE = Path(__file__).parent.parent / "data" / "chat_ids.json"
_auto_chats: Set[str] = set()


def _escape_markdown(text: str) -> str:
    """Legacy Telegram Markdown breaks (and silently drops the whole message)
    on unescaped _ * ` [ characters, which AI-generated reasoning text
    commonly contains. Escape them so a stray underscore doesn't kill the
    entire alert."""
    if not text:
        return text
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def _load_auto_chats() -> Set[str]:
    global _auto_chats
    if CHATS_FILE.exists():
        try:
            _auto_chats = set(json.loads(CHATS_FILE.read_text()))
        except Exception:
            _auto_chats = set()
    return _auto_chats


def _save_auto_chats():
    CHATS_FILE.parent.mkdir(exist_ok=True)
    CHATS_FILE.write_text(json.dumps(list(_auto_chats)))


def get_active_chat_ids() -> list:
    ids = set()
    if TELEGRAM_CHAT_ID:
        for c in TELEGRAM_CHAT_ID.replace(" ", "").split(","):
            if c.strip():
                ids.add(c.strip())
    for c in _load_auto_chats():
        ids.add(c)
    return list(ids)


async def detect_new_chats() -> int:
    if not TELEGRAM_BOT_TOKEN:
        return 0

    try:
        from telegram import Bot
        from telegram.error import TelegramError

        bot = create_bot(TELEGRAM_BOT_TOKEN)
        updates = await bot.get_updates(timeout=5)

        _load_auto_chats()
        new_count = 0

        for update in updates:
            chat = update.message.chat if update.message else None
            if chat and str(chat.id) not in _auto_chats:
                _auto_chats.add(str(chat.id))
                new_count += 1

        if new_count:
            _save_auto_chats()

        return new_count
    except Exception:
        return 0


async def start_chat_listener():
    from rich.console import Console
    console = Console()

    if not TELEGRAM_BOT_TOKEN:
        console.print("[red]No Telegram bot token configured.[/red]")
        return

    console.print(f"[cyan]Waiting for messages to bot...[/cyan]")
    console.print("[dim]Send any message to your bot on Telegram. Press Ctrl+C to stop.[/dim]\n")

    await detect_new_chats()
    ids = get_active_chat_ids()
    if ids:
        console.print(f"[green]Already detected {len(ids)} chat(s): {', '.join(ids)}[/green]")
        return

    try:
        from telegram import Bot
        bot = create_bot(TELEGRAM_BOT_TOKEN)
        last_update_id = 0

        while True:
            try:
                updates = await bot.get_updates(offset=last_update_id + 1, timeout=30)
                for update in updates:
                    last_update_id = update.update_id
                    if update.message:
                        chat = update.message.chat
                        cid = str(chat.id)
                        name = chat.first_name or chat.title or "User"

                        _load_auto_chats()
                        if cid not in _auto_chats:
                            _auto_chats.add(cid)
                            _save_auto_chats()
                            console.print(f"[green]Detected chat: {name} ({cid})[/green]")
                            await bot.send_message(chat_id=cid, text=f"Meme Coin Scanner connected! I'll send alerts here when score >{MIN_SCORE_FOR_ALERT}.")

                        ids = get_active_chat_ids()
                        if ids:
                            console.print(f"[green]Done! {len(ids)} chat(s) registered.[/green]")
                            return
            except Exception:
                await asyncio.sleep(5)
    except ImportError:
        console.print("[red]python-telegram-bot not installed[/red]")


async def send_telegram_alert(result: Dict):
    if not TELEGRAM_BOT_TOKEN:
        return

    score_data = result.get("score", {})
    total = score_data.get("total_score", 0)

    if total < MIN_SCORE_FOR_ALERT:
        return

    try:
        from telegram import Bot
        from telegram.error import TelegramError

        bot = create_bot(TELEGRAM_BOT_TOKEN)

        symbol = result.get("symbol", "???")
        name = result.get("name", "Unknown")
        verdict = score_data.get("verdict", "?")
        details = score_data.get("details", {})
        safety = details.get("safety", {})
        liquidity = details.get("liquidity", {})
        holders = details.get("holders", {})
        social = details.get("social", {})
        age = result.get("age_minutes", "?")
        url = result.get("url", "")
        mcap = liquidity.get("market_cap", 0)
        liq = liquidity.get("liquidity_usd", 0)

        verdict_emoji = {"HOT": "🔥", "POTENTIAL": "🟢", "WATCH": "🟡", "CAUTION": "⚪"}.get(verdict, "❓")

        safety_checks = safety.get("checks", {})
        mint = "✅" if safety_checks.get("mint_authority") is True else "⚠️" if safety_checks.get("mint_authority") is False else "❓"
        freeze = "✅" if safety_checks.get("freeze_authority") is True else "⚠️" if safety_checks.get("freeze_authority") is False else "❓"
        verified = "✅" if safety_checks.get("verified") else "❌"
        honeypot = safety_checks.get("honeypot_detected", "?")
        lp_locked = safety_checks.get("lp_locked_pct", 0)
        can_swap = safety_checks.get("can_swap", "?")

        hp_text = "🛑 YES" if honeypot is True else "✅ No" if honeypot is False else "❓ ?"
        swap_text = "✅ Yes" if can_swap is True else "🛑 No" if can_swap is False else "❓ ?"

        msg = (
            f"{verdict_emoji} *NEW SIGNAL: ${symbol}* ({total}/100)\n"
            f"*{name}*\n"
            f"💰 MCap: ${mcap:,.0f} | Liq: ${liq:,.0f}\n"
            f"🔒 Mint: {mint} | Freeze: {freeze} | Verified: {verified}\n"
            f"📦 LP Locked: {lp_locked}% | Honeypot: {hp_text}\n"
            f"🔄 Swap: {swap_text}\n"
            f"👥 Holders: {holders.get('total_holders', 0)} (Top10: {holders.get('top10_concentration_pct', 0)}%)\n"
            f"🌐 Social: {', '.join(social.get('links', [])) or 'none'}\n"
            f"⏱️ Age: {age:.0f}m" if isinstance(age, (int, float)) else f"⏱️ Age: {age}"
            f"\n📊 {url}"
        )

        chat_ids = get_active_chat_ids()
        for cid in chat_ids:
            asyncio.create_task(_send_telegram_alert(bot, cid, msg))

    except ImportError:
        pass
    except Exception:
        pass


async def _send_telegram_alert(bot, chat_id: str, message: str):
    try:
        from telegram.error import TelegramError
        try:
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown", disable_web_page_preview=True)
        except TelegramError as e:
            # Markdown parse failures used to silently drop the alert with no
            # trace. Log it, and retry once as plain text so the user still
            # gets the signal even if formatting is imperfect.
            logger.warning(f"Telegram send failed for chat {chat_id} with Markdown ({e}); retrying as plain text")
            try:
                await bot.send_message(chat_id=chat_id, text=message, disable_web_page_preview=True)
            except TelegramError as e2:
                logger.error(f"Telegram send failed for chat {chat_id} even as plain text: {e2}")
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram alert to {chat_id}: {e}")


async def send_ai_signal(result: Dict, ai_result: Dict):
    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        bot = create_bot(TELEGRAM_BOT_TOKEN)

        symbol = _escape_markdown(result.get("symbol", "???"))
        name = _escape_markdown(result.get("name", "Unknown"))
        score = result.get("score", {}).get("total_score", 0)
        mcap = result.get("market_cap", 0)
        liq = result.get("liquidity_usd", 0)
        price = result.get("price_usd", 0)
        price_ch = result.get("price_change_24h", 0) or 0
        age = result.get("age_minutes", "?")
        url = result.get("url", "")
        charts = result.get("charts", {})

        signal = ai_result.get("signal", "BUY")
        confidence = ai_result.get("confidence", "?")
        reasoning = _escape_markdown(ai_result.get("reasoning", ""))
        target = _escape_markdown(str(ai_result.get("target_price_pct", "N/A")))
        stop_loss = _escape_markdown(str(ai_result.get("stop_loss_pct", "N/A")))
        risk = ai_result.get("risk_level", "medium")
        position = _escape_markdown(str(ai_result.get("position_size", "1-3%")))
        strengths = ai_result.get("key_strengths", [])
        risks = ai_result.get("key_risks", [])
        source = ai_result.get("source", "ai")

        sig_emoji = {"STRONG_BUY": "🔥", "BUY": "🟢", "WATCH": "🟡", "AVOID": "🔴"}.get(signal, "❓")
        source_label = "🤖 AI" if source == "ai" else "📊 Engine"

        pc_emoji = "📈" if price_ch > 0 else "📉"

        msg = (
            f"{sig_emoji} {source_label} *SIGNAL: ${symbol} — {signal} ({confidence}/10)*\n"
            f"*{name}*\n"
            f"{'─' * 25}\n"
            f"💡 *AI Analysis:*\n"
            f"_{reasoning}_\n"
            f"{'─' * 25}\n"
            f"📊 Score: {score}/100 | 💰 ${mcap:,.0f} MCap | ${liq:,.0f} Liq\n"
            f"💵 Price: ${price:.8f} | {pc_emoji} {price_ch:+.0f}%\n"
            f"🎯 Target: {target} | 🛑 Stop: {stop_loss}\n"
            f"⚡ Risk: {risk} | 📦 Position: {position}\n"
        )

        if strengths:
            msg += f"✅ {', '.join(strengths[:2])}\n"
        if risks:
            msg += f"⚠️ {', '.join(risks[:2])}\n"

        age_str = f"{age:.0f}m" if isinstance(age, (int, float)) else str(age)
        msg += f"⏱️ {age_str}"

        if charts.get("price_chart"):
            msg += f" | [Chart]({charts['price_chart']})"
        if url:
            msg += f" | [DexScreener]({url})"

        chat_ids = get_active_chat_ids()
        if not chat_ids:
            logger.warning("send_ai_signal: no active chat_ids to send to (bot has no linked chats yet)")
        for cid in chat_ids:
            asyncio.create_task(_send_telegram_alert(bot, cid, msg))

    except Exception as e:
        logger.error(f"send_ai_signal failed before message could be built/sent: {e}")
