import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memecoin-bot")

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL, PORT
from utils.telegram_client import create_bot
from core.bot_handler import handle_command
from core.auto_signal import start_auto_signal, set_auto_running

bot = None
app_lifespan_started = False
_auto_signal_task = None
_position_monitor_task = None
_poll_task = None


async def _poll_updates():
    last_update_id = 0
    while True:
        try:
            updates = await bot.get_updates(offset=last_update_id + 1, timeout=30)
            for update in updates:
                last_update_id = update.update_id
                if not update.message or not update.message.text:
                    continue
                text = update.message.text.strip()
                chat = update.message.chat
                chat_id = str(chat.id)
                chat_name = chat.first_name or chat.title or "User"
                logger.info(f"@{chat_name} ({chat_id}): {text}")
                if text.startswith("/"):
                    parts = text.split(maxsplit=1)
                    cmd_part = parts[0][1:].lower().split("@")[0]
                    args = parts[1] if len(parts) > 1 else ""
                    asyncio.create_task(_process_command(cmd_part, chat_id, args, chat_name))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, app_lifespan_started, _auto_signal_task, _poll_task

    logger.info("Starting Meme Coin Scanner Bot...")
    bot = create_bot(TELEGRAM_BOT_TOKEN)

    if WEBHOOK_URL:
        webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        try:
            await bot.set_webhook(webhook_endpoint)
            logger.info(f"Webhook set: {webhook_endpoint}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            logger.info("Falling back to polling mode")
            _poll_task = asyncio.create_task(_poll_updates())
            logger.info("Polling mode started (fallback)")
    else:
        logger.info("No WEBHOOK_URL set, starting polling mode...")
        _poll_task = asyncio.create_task(_poll_updates())
        logger.info("Polling mode started")

    try:
        commands = [
            ("start", "Mulai bot dan deteksi chat"),
            ("scan", "Quick scan trending meme coin"),
            ("filter", "Custom filter scan"),
            ("live", "Live scan real-time"),
            ("pumpfun", "Scan Pump.fun launches"),
            ("deepscan", "Deep scan 50+ coins"),
            ("score", "Analisis token by address"),
            ("ai", "Analisis token dengan AI + charts"),
            ("gem", "Gem hunter: koin potensial naik ribuan %"),
            ("wallet", "Link/unlink wallet Solana"),
            ("autotrade", "Auto trade on/off/mode"),
            ("buy", "Manual buy token"),
            ("sell", "Manual sell token"),
            ("positions", "Lihat posisi terbuka + P&L"),
            ("rugcheck", "Cek rug risk token"),
            ("compare", "Bandingkan 2 token side by side"),
            ("verify", "Verifikasi kontrak token"),
            ("report", "Laporan trading + stats"),
            ("sellmode", "Advanced sell settings"),
            ("perf", "Signal performance + market"),
            ("bundler", "Cek aktivitas bundler"),
            ("spikes", "Cek volume spike terbaru"),
            ("wl", "Lihat watchlist"),
            ("wladd", "Tambah ke watchlist"),
            ("wlremove", "Hapus dari watchlist"),
            ("whales", "Scan / auto-detect whales"),
            ("whalefolio", "Portfolio whale wallets"),
            ("whaleadd", "Tambah whale wallet"),
            ("whaleremove", "Hapus whale wallet"),
            ("deployer", "Cek history deployer"),
            ("deployers", "Daftar deployer"),
            ("deployeradd", "Tambah deployer"),
            ("smartmoney", "Cek smart money & insider"),
            ("narratives", "Sector momentum ranking"),
            ("autoscan", "Auto signal on/off"),
            ("autostatus", "Status auto signal"),
            ("signals", "Riwayat sinyal 24 jam"),
            ("export", "Export scan ke CSV"),
            ("chats", "Daftar chat terdaftar"),
            ("help", "Bantuan perintah"),
        ]
        await bot.set_my_commands(commands)
        logger.info(f"Bot commands registered: {len(commands)}")
    except Exception as e:
        logger.warning(f"Cannot register bot commands: {e}")

    app_lifespan_started = True

    logger.info("Starting auto signal broadcaster...")
    _auto_signal_task = asyncio.create_task(start_auto_signal())
    logger.info("Auto signal broadcaster running in background")

    from core.rug_monitor import position_monitor_loop
    _position_monitor_task = asyncio.create_task(position_monitor_loop())
    logger.info("Position monitor running in background")
    yield

    logger.info("Shutting down...")
    set_auto_running(False)
    if _auto_signal_task:
        _auto_signal_task.cancel()
    if _position_monitor_task:
        _position_monitor_task.cancel()
    if _poll_task:
        _poll_task.cancel()
    if bot and WEBHOOK_URL:
        try:
            await bot.delete_webhook()
        except Exception:
            pass
    from utils.client import HttpClient
    client = await HttpClient.get_instance()
    await client.close()


app = FastAPI(title="Meme Coin Scanner Bot", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "online", "bot": "Meme Coin Scanner", "commands": 20}


@app.get("/health")
async def health():
    me = None
    if bot:
        try:
            me = await bot.get_me()
        except Exception:
            pass
    return {
        "status": "healthy",
        "bot": me.username if me else "not connected",
        "pid": os.getpid(),
    }


@app.post("/webhook")
async def webhook(request: Request):
    if not bot:
        return Response(status_code=200)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, 400)

    update_id = data.get("update_id")

    message = data.get("message") or data.get("edited_message")
    if not message:
        return Response(status_code=200)

    text = message.get("text", "").strip()
    chat = message.get("chat", {})
    chat_id = str(chat.get("id", ""))
    chat_name = chat.get("first_name", chat.get("title", "User"))

    if not text or not chat_id:
        return Response(status_code=200)

    logger.info(f"@{chat_name} ({chat_id}): {text}")

    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd_part = parts[0][1:].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""
        asyncio.create_task(_process_command(cmd_part, chat_id, args, chat_name))

    return Response(status_code=200)


async def _process_command(cmd_part: str, chat_id: str, args: str, chat_name: str):
    try:
        from alerts.telegram import send_loading, edit_message
        loading_id = await send_loading(chat_id)
        reply = await handle_command(cmd_part, chat_id, args)
        if loading_id:
            await edit_message(chat_id, loading_id, reply)
        else:
            try:
                await bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown", disable_web_page_preview=True)
            except Exception:
                try:
                    await bot.send_message(chat_id=chat_id, text=reply, disable_web_page_preview=True)
                except Exception as e:
                    logger.error(f"Failed to send reply: {e}")
    except Exception as e:
        logger.error(f"Command error: {e}")
        try:
            await bot.send_message(chat_id=chat_id, text=f"Error: {str(e)[:200]}")
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    if not WEBHOOK_URL and app_lifespan_started:
        logger.info("Running polling mode...")
        async def run():
            from config import SECRET_KEY
            uvicorn.run(app, host="0.0.0.0", port=PORT)
        asyncio.run(run())
    else:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
