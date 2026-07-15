import asyncio
import sys
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.spinner import Spinner
from rich.table import Table
from rich import box

from config import (
    SCAN_INTERVAL_SECONDS,
    MIN_LIQUIDITY_USD,
    MAX_MARKET_CAP_USD,
    MAX_TOKEN_AGE_MINUTES,
    MIN_HOLDER_COUNT,
    MIN_SCORE_FOR_ALERT,
)
from core.dexscreener import fetch_new_pairs, fetch_trending_solana, get_token_info
from core.pumpfun import fetch_new_launches
from analyzers.safety import check_safety
from analyzers.liquidity import analyze_liquidity
from analyzers.holder import analyze_holder_distribution
from analyzers.scorer import calculate_social_score, calculate_final_score
from analyzers.professional import determine_signal
from alerts.console import print_banner, build_results_table, print_token_detail
from alerts.telegram import send_telegram_alert, start_chat_listener, detect_new_chats
from core.bot_handler import handle_command
from core.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist, add_price_snapshot, check_watchlist_alerts, get_watchlist_item
from core.volume_tracker import record_volume, detect_spikes
from core.migration_alert import detect_migrations_from_scan
from core.bundler_detector import detect_bundler_activity
from core.whale_tracker import load_known_whales, add_whale, remove_whale, scan_whale_buys, save_whales, check_whale_holds_token, scan_whale_portfolios
from core.whale_detector import detect_whales_for_token
from core.deep_scanner import deep_scan
from core.deployer_check import analyze_token_deployer
from core.deployer_tracker import load_deployer_list, add_deployer, remove_deployer, scan_deployer_new_tokens
from core.smart_money import (
    analyze_smart_money, record_early_buyers, add_smart_wallet, remove_smart_wallet, load_smart_wallets,
)
from core.narratives import classify_narrative, track_sector_momentum, get_narrative_momentum
from utils.client import HttpClient
from utils.export import export_json, export_csv

console = Console()
running = True


def signal_handler(sig, frame):
    global running
    running = False


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
        "labels": pair_data.get("labels", []),
        "score": score,
    }

    if token_address:
        record_volume(token_address, result["symbol"], result["volume_24h"], result["market_cap"], result["liquidity_usd"])
        wl = get_watchlist_item(token_address)
        if wl:
            add_price_snapshot(token_address, result["price_usd"], result["market_cap"], result["volume_24h"])

        if age_minutes < 30:
            bundler = await detect_bundler_activity(token_address)
            result["bundler_check"] = bundler

        deployer = await analyze_token_deployer(token_address)
        result["deployer_check"] = deployer

        whale_holds = await check_whale_holds_token(token_address)
        result["whale_holders"] = whale_holds

        auto_whales = await detect_whales_for_token(token_address, max_holders=30)
        result["auto_whales"] = auto_whales

        if deployer.get("found"):
            stats = deployer.get("stats", {})
            deployer_status = stats.get("status", "unknown")
            if deployer_status == "trusted":
                result["score"]["total_score"] = min(100, result["score"]["total_score"] + 5)
                result["score"]["deployer_bonus"] = "+5 trusted"
            elif deployer_status == "suspicious":
                result["score"]["total_score"] = max(0, result["score"]["total_score"] - 15)
                result["score"]["deployer_penalty"] = "-15 rug history"

        result["narratives"] = classify_narrative(
            pair_data.get("base_token", {}).get("name", ""),
            pair_data.get("base_token", {}).get("symbol", ""),
        )

        if age_minutes < 120:
            early = []
            for w in result.get("auto_whales", {}).get("whales", []):
                if w.get("wallet"):
                    early.append(w["wallet"])
            for w in result.get("auto_whales", {}).get("dolphins", []):
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


async def deep_scan_mode():
    print_banner()
    await detect_new_chats()
    console.print("[bold cyan]Deep Scan Mode[/bold cyan] — 4 sources combined\n")
    console.print("[dim]Sources: DexScreener + Multi-keyword + Pump.fun + Jupiter[/dim]\n")

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Deep scanning 4 sources...", total=None)
        pairs = await deep_scan(max_age_minutes=120, max_results=60)

    if not pairs:
        console.print("[yellow]No pairs found.[/yellow]")
        return

    console.print(f"[dim]Found {len(pairs)} unique pairs. Filtering & analyzing...[/dim]\n")

    results = []
    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]Analyzing...", total=len(pairs))
        for pair in pairs:
            liq = pair.get("liquidity_usd", 0)
            mcap = pair.get("market_cap", 0)
            if liq < 1000 or mcap < 500:
                progress.advance(task)
                continue
            analyzed = await analyze_token(pair)
            results.append(analyzed)
            progress.advance(task)

            if analyzed["score"]["total_score"] >= MIN_SCORE_FOR_ALERT:
                await send_telegram_alert(analyzed)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)
    results = results[:50]

    console.clear()
    print_banner()
    console.print(f"[dim]Deep Scan: {len(results)} tokens analyzed from {len(pairs)} found[/dim]")
    console.print(build_results_table(results))

    spikes = detect_spikes()
    if spikes:
        console.print(f"\n[bold yellow]VOLUME SPIKES:[/bold yellow]")
        for sp in spikes[:3]:
            console.print(f"  {sp['symbol']}: +{sp['spike_pct']}%")

    migrations = detect_migrations_from_scan(results)
    if migrations:
        console.print(f"\n[bold green]MIGRATIONS:[/bold green]")
        for mig in migrations:
            console.print(f"  {mig['symbol']}: {mig['from_market']} -> {mig['to_market']}")

    if results:
        console.print(f"\n[bold]Top 3 with charts:[/bold]")
        for r in results[:3]:
            print_token_detail(r)

    return results


async def live_scan():
    print_banner()
    await detect_new_chats()
    console.print("[dim]Live scan mode — Ctrl+C to stop[/dim]\n")
    console.print(f"[yellow]Filters:[/yellow] Liq >${MIN_LIQUIDITY_USD:,.0f} | MCap <${MAX_MARKET_CAP_USD:,.0f} | Age <{MAX_TOKEN_AGE_MINUTES}m | Score >{MIN_SCORE_FOR_ALERT}")
    console.print(f"[yellow]Interval:[/yellow] {SCAN_INTERVAL_SECONDS}s\n")

    seen = set()

    while running:
        try:
            pairs = await fetch_trending_solana()
            new_pairs = [p for p in pairs if p.get("pair_address") not in seen]
            if not new_pairs:
                console.print(f"[dim]Last scan: {datetime.now().strftime('%H:%M:%S')} | No new pairs found[/dim]")
            results = []

            with Progress(
                SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console, transient=True
            ) as progress:
                task = progress.add_task("[cyan]Scanning trending...", total=len(new_pairs))
                for pair in new_pairs:
                    seen.add(pair.get("pair_address", ""))
                    liq = pair.get("liquidity_usd", 0)
                    mcap = pair.get("market_cap", 0)

                    if liq < MIN_LIQUIDITY_USD or mcap > MAX_MARKET_CAP_USD:
                        progress.advance(task)
                        continue

                    analyzed = await analyze_token(pair)
                    results.append(analyzed)
                    progress.advance(task)

                    if analyzed["score"]["total_score"] >= MIN_SCORE_FOR_ALERT:
                        await send_telegram_alert(analyzed)

            results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

            console.clear()
            print_banner()
            console.print(f"[dim]Last scan: {datetime.now().strftime('%H:%M:%S')} | New: {len(results)} | Total seen: {len(seen)}[/dim]")
            console.print(build_results_table(results))

            spikes = detect_spikes()
            if spikes:
                console.print(f"\n[bold yellow]VOLUME SPIKE DETECTED:[/bold yellow]")
                for sp in spikes[:3]:
                    console.print(f"  [yellow]{sp['symbol']}:[/yellow] +{sp['spike_pct']}% (${sp['volume_now']:,.0f}) in {sp['time_diff_minutes']}m")

            wl_alerts = check_watchlist_alerts()
            if wl_alerts:
                console.print(f"\n[bold magenta]WATCHLIST ALERTS:[/bold magenta]")
                for wa in wl_alerts[:3]:
                    emoji = "📉" if wa["alert_type"] == "price_drop" else "📈"
                    console.print(f"  {emoji} {wa['symbol']}: {wa['change_pct']:+.1f}%")

            migrations = detect_migrations_from_scan(results)
            if migrations:
                console.print(f"\n[bold green]DEX MIGRATIONS DETECTED:[/bold green]")
                for mig in migrations:
                    console.print(f"  [green]{mig['symbol']}:[/green] {mig['from_market']} -> {mig['to_market']} (Bullish signal!)")

            bundled = [r for r in results if r.get("bundler_check", {}).get("is_bundled")]
            if bundled:
                console.print(f"\n[bold red]BUNDLER WARNING:[/bold red]")
                for b in bundled:
                    c = b["bundler_check"]
                    console.print(f"  [red]{b['symbol']}:[/red] {c['rapid_buys_under_60s']} buys in <60s ({c['unique_buyers_first_5min']} wallets)")

            deployer_alerts = scan_deployer_new_tokens()
            if deployer_alerts:
                console.print(f"\n[bold blue]DEPLOYER ALERTS:[/bold blue]")
                for da in deployer_alerts[:5]:
                    console.print(f"  [cyan]{da['deployer_name']}[/cyan] deployed {da['token_mint'][:12]}...")

            if not running:
                break
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

        except Exception as e:
            console.print(f"[red]Scan error: {e}[/red]")
            await asyncio.sleep(10)


async def quick_scan():
    print_banner()
    await detect_new_chats()
    console.print("[dim]Quick scan mode — one-time scan[/dim]\n")

    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("[cyan]Fetching trending pairs from DexScreener...", total=None)
        pairs = await fetch_trending_solana()

    console.print(f"[dim]Fetched {len(pairs)} pairs. Filtering...[/dim]")

    filtered = [p for p in pairs if p.get("liquidity_usd", 0) >= MIN_LIQUIDITY_USD]
    filtered = [p for p in filtered if p.get("market_cap", 0) <= MAX_MARKET_CAP_USD]
    filtered = filtered[:30]

    console.print(f"[dim]Analyzing {len(filtered)} tokens...[/dim]")

    results = []
    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("[cyan]Scanning...", total=len(filtered))
        for pair in filtered:
            analyzed = await analyze_token(pair)
            results.append(analyzed)
            progress.advance(task)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    console.clear()
    print_banner()
    console.print(build_results_table(results))

    for r in results:
        total = r["score"]["total_score"]
        if total >= MIN_SCORE_FOR_ALERT:
            await send_telegram_alert(r)

    if results:
        console.print(f"\n[bold]Top 3 signals:[/bold]")
        for r in results[:3]:
            print_token_detail(r)

    return results


async def pumpfun_scan():
    print_banner()
    console.print("[dim]Pump.fun scan mode[/dim]\n")

    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("[cyan]Fetching recent Pump.fun launches...", total=None)
        coins = await fetch_new_launches(limit=20)

    console.print(f"[dim]Found {len(coins)} recent Pump.fun tokens[/dim]")

    results = []
    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("[cyan]Analyzing...", total=len(coins))
        for coin in coins:
            token_addr = coin.get("mint", "")
            safety_result = await check_safety(token_addr)
            holder_result = await analyze_holder_distribution(token_addr)

            social_score = 0
            links = []
            if coin.get("twitter"):
                links.append("twitter")
                social_score += 33
            if coin.get("telegram"):
                links.append("telegram")
                social_score += 33
            if coin.get("website"):
                links.append("website")
                social_score += 34
            social_result = {"score": min(social_score, 100), "has_socials": bool(links), "links": links, "is_meme_keyword": False}

            liquidity_result = {
                "score": 30, "checks": {"liq_depth": "pumpfun"}, "risk": "medium",
                "liquidity_usd": coin.get("market_cap_sol", 0), "market_cap": coin.get("market_cap_sol", 0), "volume_24h": 0,
            }

            score = await calculate_final_score(safety_result, liquidity_result, holder_result, social_result, {})

            results.append({
                "name": coin.get("name", "Unknown"),
                "symbol": coin.get("symbol", "???"),
                "token_address": token_addr,
                "pair_address": "",
                "price_usd": 0,
                "liquidity_usd": coin.get("market_cap_sol", 0),
                "market_cap": coin.get("market_cap_sol", 0),
                "volume_24h": 0,
                "url": f"https://pump.fun/{token_addr}",
                "dex": "pump.fun",
                "age_minutes": 0,
                "labels": [],
                "score": score,
            })
            progress.advance(task)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    console.clear()
    print_banner()
    console.print(build_results_table(results))

    for r in results:
        if r["score"]["total_score"] >= MIN_SCORE_FOR_ALERT:
            await send_telegram_alert(r)

    return results


async def run_export():
    results = await quick_scan()
    if not results:
        console.print("[yellow]No results to export.[/yellow]")
        return

    exportable = []
    for r in results:
        s = r["score"]
        exportable.append({
            "symbol": r["symbol"],
            "name": r["name"],
            "token_address": r["token_address"],
            "score": s["total_score"],
            "verdict": s["verdict"],
            "market_cap": r["market_cap"],
            "liquidity_usd": r["liquidity_usd"],
            "volume_24h": r["volume_24h"],
            "holders": s["details"]["holders"]["total_holders"],
            "top10_pct": s["details"]["holders"]["top10_concentration_pct"],
            "safety_score": s["details"]["safety"]["score"],
            "url": r["url"],
        })

    json_path = export_json(exportable)
    csv_path = export_csv(exportable)
    console.print(f"\n[green]Exported to:[/green] {json_path}")
    console.print(f"[green]Exported to:[/green] {csv_path}")


async def config_wizard():
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    console.print(Panel.fit("[bold]Configuration Wizard[/bold]", border_style="cyan"))
    console.print()

    token = Prompt.ask("Telegram Bot Token", default=TELEGRAM_BOT_TOKEN)
    chat_id = Prompt.ask("Telegram Chat ID (user/group)", default=TELEGRAM_CHAT_ID)

    config_path = Path(__file__).parent / "config.py"
    content = config_path.read_text(encoding="utf-8")

    content = content.replace(f'TELEGRAM_BOT_TOKEN = "{TELEGRAM_BOT_TOKEN}"', f'TELEGRAM_BOT_TOKEN = "{token}"')
    content = content.replace(f'TELEGRAM_CHAT_ID = "{TELEGRAM_CHAT_ID}"', f'TELEGRAM_CHAT_ID = "{chat_id}"')

    config_path.write_text(content, encoding="utf-8")
    console.print("\n[green]Configuration saved![/green]")


async def run_telegram_bot():
    from config import TELEGRAM_BOT_TOKEN
    from telegram import Bot
    from core.bot_handler import handle_command
    from utils.telegram_client import create_bot

    if not TELEGRAM_BOT_TOKEN:
        console.print("[red]Telegram bot token tidak ada. Gunakan menu Config (5) untuk set.[/red]")
        return

    print_banner()
    console.print("[cyan]Telegram Bot Mode[/cyan]")
    console.print("[dim]Bot akan merespon command. Kirim /help ke bot kamu di Telegram.[/dim]")
    console.print("[dim]Pastikan sudah kirim /start ke bot sebelum menggunakan command lain.[/dim]\n")

    bot = create_bot(TELEGRAM_BOT_TOKEN)

    try:
        me = await bot.get_me()
        console.print(f"[green]Bot connected: @{me.username}[/green]")
    except Exception:
        console.print("[red]Cannot connect to Telegram API (network blocked?)[/red]")
        console.print("[yellow]Gunakan @BotFather untuk set bot commands secara manual.[/yellow]")
        console.print("[dim]Command yang bisa di-copy ke @BotFather > Edit Bot > Edit Commands:[/dim]")
        console.print("""
start - Mulai bot dan deteksi chat ID
scan - Quick scan trending meme coin
live - Live scan real-time monitoring
pumpfun - Scan Pump.fun launches terbaru
score - Analisis token spesifik (usage: /score &lt;address&gt;)
chats - Lihat daftar chat terdaftar
help - Bantuan perintah
""")
        return

    try:
        commands = [
            ("start", "Mulai bot dan deteksi chat ID"),
            ("scan", "Quick scan trending meme coin"),
            ("filter", "Custom filter scan (aggressive/balanced/conservative)"),
            ("live", "Live scan real-time monitoring"),
            ("pumpfun", "Scan Pump.fun launches terbaru"),
            ("deepscan", "Deep scan 50+ coins from 4 sources"),
            ("autoscan", "Auto signal on/off/status"),
            ("autostatus", "Cek status auto signal"),
            ("signals", "Riwayat sinyal 24 jam"),
            ("score", "Analisis token by address"),
            ("bundler", "Cek aktivitas bundler"),
            ("spikes", "Cek volume spike terbaru"),
            ("wl", "Lihat watchlist"),
            ("wladd", "Tambah token ke watchlist"),
            ("wlremove", "Hapus dari watchlist"),
            ("whales", "Scan whale wallet buys"),
            ("whaleadd", "Tambah whale wallet"),
            ("whaleremove", "Hapus whale wallet"),
            ("whalefolio", "Lihat portfolio semua whale"),
            ("deployer", "Cek history deployer token"),
            ("deployers", "Lihat daftar deployer ditrack"),
            ("deployeradd", "Tambah deployer wallet"),
            ("export", "Export scan ke CSV"),
            ("chats", "Daftar chat terdaftar"),
            ("help", "Bantuan perintah"),
        ]
        await bot.set_my_commands(commands)
        console.print("[green]Bot commands registered via API[/green]")
    except Exception:
        console.print("[yellow]Cannot set commands via API. Use @BotFather to set them manually.[/yellow]")

    console.print("\n[cyan]Listening for commands... Press Ctrl+C to stop[/cyan]\n")

    last_update_id = 0

    while running:
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

                console.print(f"[dim]@{chat_name}: {text}[/dim]")

                if text.startswith("/"):
                    parts = text.split(maxsplit=1)
                    cmd_part = parts[0][1:].lower().split("@")[0]
                    args = parts[1] if len(parts) > 1 else ""

                    from alerts.telegram import send_loading, edit_message
                    loading_id = await send_loading(chat_id)

                    reply = await handle_command(cmd_part, chat_id, args)

                    if loading_id:
                        await edit_message(chat_id, loading_id, reply)
                    else:
                        try:
                            await bot.send_message(
                                chat_id=chat_id, text=reply,
                                parse_mode="Markdown", disable_web_page_preview=True
                            )
                        except Exception:
                            try:
                                await bot.send_message(chat_id=chat_id, text=reply, disable_web_page_preview=True)
                            except Exception:
                                pass

        except asyncio.CancelledError:
            break
        except Exception as e:
            console.print(f"[red]Bot error: {e}[/red]")
            await asyncio.sleep(5)

    console.print("[dim]Bot stopped.[/dim]")


async def analyze_by_address():
    print_banner()
    from rich.prompt import Prompt

    address = Prompt.ask("[cyan]Paste token address[/cyan]").strip()
    if not address:
        console.print("[red]Address empty[/red]")
        return

    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("[cyan]Fetching token data...", total=None)
        info = await get_token_info(address)

    if not info:
        console.print(f"[red]Token tidak ditemukan: {address}[/red]")
        return

    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        progress.add_task("[cyan]Analyzing...", total=None)
        result = await analyze_token(info)

    console.clear()
    print_banner()
    print_token_detail(result)

    result_list = [result]
    console.print(build_results_table(result_list))


async def custom_filter_scan():
    from rich.prompt import Prompt
    from config import FILTER_PRESETS

    print_banner()
    console.print("[bold cyan]Custom Filter Mode[/bold cyan]\n")

    console.print("[bold]Filter Presets:[/bold]")
    for key, preset in FILTER_PRESETS.items():
        console.print(f"  [{key}] {preset['name']}")
        console.print(f"      Liq >${preset['liq_min']:,} | MCap <${preset['mcap_max']:,} | Age <{preset['age_max']}m | Holders >{preset['holders_min']} | Score >{preset['score_min']}")
    console.print(f"  [manual] Set custom values")
    console.print()

    choice = Prompt.ask("Select filter preset", choices=list(FILTER_PRESETS.keys()) + ["manual"], default="balanced")

    if choice == "manual":
        liq_min = float(Prompt.ask("Min liquidity USD", default="3000"))
        mcap_max = float(Prompt.ask("Max market cap USD", default="2000000"))
        age_max = int(Prompt.ask("Max token age (minutes)", default="120"))
        holders_min = int(Prompt.ask("Min holders", default="10"))
        score_min = int(Prompt.ask("Min score", default="50"))
    else:
        p = FILTER_PRESETS[choice]
        liq_min = p["liq_min"]
        mcap_max = p["mcap_max"]
        age_max = p["age_max"]
        holders_min = p["holders_min"]
        score_min = p["score_min"]

    use_multi_query = Prompt.ask("Multi-query deep scan? (search many keywords)", choices=["y", "n"], default="n") == "y"

    console.print(f"\n[yellow]Filters:[/yellow] Liq >${liq_min:,.0f} | MCap <${mcap_max:,.0f} | Age <{age_max}m | Holders >{holders_min} | Score >{score_min}")
    console.print()

    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("[cyan]Scanning...", total=None)

        if use_multi_query:
            from config import MEME_SEARCH_TERMS
            all_pairs = []
            for term in MEME_SEARCH_TERMS:
                from core.dexscreener import fetch_new_pairs
                pairs = await fetch_new_pairs(term, max_age_minutes=age_max)
                all_pairs.extend(pairs)
                await asyncio.sleep(0.5)
            pairs = {p["pair_address"]: p for p in all_pairs if p["pair_address"]}.values()
            pairs = list(pairs)
            console.print(f"[dim]Multi-query found {len(pairs)} unique pairs[/dim]")
        else:
            pairs = await fetch_trending_solana()

    results = []
    seen_addr = set()

    with Progress(
        SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("[cyan]Analyzing...", total=len(pairs))
        for pair in pairs:
            seen_addr.add(pair.get("pair_address", ""))
            liq = pair.get("liquidity_usd", 0)
            mcap = pair.get("market_cap", 0)
            age = pair.get("age_minutes", 0)

            if liq < liq_min or mcap > mcap_max or age > age_max:
                progress.advance(task)
                continue

            analyzed = await analyze_token(pair)

            holder_count = analyzed["score"]["details"].get("holders", {}).get("total_holders", 0)
            if isinstance(holder_count, str):
                holder_count = 0
            if holder_count < holders_min:
                progress.advance(task)
                continue

            if analyzed["score"]["total_score"] < score_min:
                progress.advance(task)
                continue

            results.append(analyzed)
            progress.advance(task)

    results.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    console.clear()
    print_banner()
    console.print(f"[dim]Filter: Liq>${liq_min:,} | MCap<${mcap_max:,} | Age<{age_max}m | Holders>{holders_min} | Score>{score_min}[/dim]")
    console.print(build_results_table(results))

    for r in results:
        if r["score"]["total_score"] >= score_min:
            await send_telegram_alert(r)

    if results:
        console.print(f"\n[bold]Top signal:[/bold]")
        print_token_detail(results[0])


async def view_watchlist():
    print_banner()
    items = load_watchlist()

    if not items:
        console.print("[dim]Watchlist is empty. Add tokens via menu 11 or from scan results.[/dim]\n")
        console.print("Usage: /score <address> or scan results will auto-track watchlist tokens.\n")
        return

    console.print(f"[bold cyan]Watchlist[/bold cyan] ({len(items)} tokens)\n")

    table = Table(title="", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Token", style="bold", width=14)
    table.add_column("MCap Now", justify="right", width=10)
    table.add_column("MCap Added", justify="right", width=10)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Change", justify="right", width=8)
    table.add_column("Added", width=12)

    for item in items:
        current_mcap = item.get("current_mcap", 0)
        added_mcap = item.get("mcap_added", 0)
        current_price = item.get("current_price", 0)
        change = 0
        if added_mcap > 0 and current_mcap > 0:
            change = ((current_mcap - added_mcap) / added_mcap) * 100

        change_str = f"[green]+{change:.0f}%[/green]" if change > 0 else f"[red]{change:.0f}%[/red]" if change < 0 else "-"
        table.add_row(
            item.get("symbol", "???"),
            f"${current_mcap:,.0f}" if current_mcap else "$?",
            f"${added_mcap:,.0f}" if added_mcap else "$?",
            f"${current_price:.8f}" if current_price else "$?",
            change_str,
            item.get("added_at", "?")[:10],
        )

    console.print(table)

    console.print("\n[dim]Price updates when token appears in any scan.[/dim]")


async def add_to_watchlist_mode():
    print_banner()
    from rich.prompt import Prompt

    address = Prompt.ask("[cyan]Paste token address to add[/cyan]").strip()
    if not address:
        return

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Fetching token...", total=None)
        info = await get_token_info(address)

    if not info:
        console.print(f"[red]Token not found: {address}[/red]")
        return

    sym = info.get("base_token", {}).get("symbol", "???")
    name = info.get("base_token", {}).get("name", "Unknown")
    mcap = info.get("market_cap", 0)
    liq = info.get("liquidity_usd", 0)
    url = info.get("url", "")

    item = add_to_watchlist(address, sym, name, mcap, liq, url)
    console.print(f"[green]Added {sym} to watchlist![/green]")
    console.print(f"  MCap: ${mcap:,.0f} | Liq: ${liq:,.0f} | Alerts: drop -50%, rise +100%")


async def remove_watchlist_mode():
    print_banner()
    from rich.prompt import Prompt

    items = load_watchlist()
    if not items:
        console.print("[dim]Watchlist empty.[/dim]")
        return

    console.print("[bold]Current watchlist:[/bold]")
    for i, item in enumerate(items, 1):
        console.print(f"  [{i}] {item['symbol']} - {item['name'][:25]} ({item['address'][:12]}...)")

    choice = Prompt.ask("Select number to remove (0=cancel)", default="0")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            addr = items[idx]["address"]
            if remove_from_watchlist(addr):
                console.print(f"[green]Removed {items[idx]['symbol']} from watchlist.[/green]")
            return
    except (ValueError, IndexError):
        pass
    console.print("[dim]Cancelled.[/dim]")


async def whale_scan():
    print_banner()
    console.print("[bold cyan]Whale Wallet Scanner[/bold cyan]\n")
    console.print("[dim]Scanning tracked whale wallets for recent token buys...[/dim]\n")

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Scanning whales...", total=None)
        buys = await scan_whale_buys(min_volume_sol=0.05)

    if not buys:
        console.print("[dim]No new whale buys detected or no whale wallets configured.[/dim]")
        console.print(f"[dim]Whales tracked: {len(load_known_whales())}. Add via 'Add Whale' menu.[/dim]")
        return

    console.print(f"[bold]Recent Whale Activity:[/bold]\n")
    for b in buys[:10]:
        ts = datetime.fromtimestamp(b["time"], tz=timezone.utc).strftime("%H:%M") if b["time"] else "?"
        console.print(f"  [cyan]{b['wallet_name']}[/cyan] bought {b['token_mint'][:12]}... ({ts}) | {b['amount_sol']:.3f} SOL")


async def add_whale_mode():
    print_banner()
    from rich.prompt import Prompt
    address = Prompt.ask("[cyan]Paste whale wallet address[/cyan]").strip()
    if not address:
        return
    name = Prompt.ask("[cyan]Nickname (optional)[/cyan]", default="").strip()
    result = add_whale(address, name)
    console.print(f"[green]Whale added: {result['name']} ({address[:12]}...)[/green]")
    console.print(f"[dim]Tracked whales: {len(load_known_whales())}[/dim]")


async def remove_whale_mode():
    print_banner()
    from rich.prompt import Prompt
    whales = load_known_whales()
    if not whales:
        console.print("[dim]No whales tracked.[/dim]")
        return
    for i, w in enumerate(whales, 1):
        console.print(f"  [{i}] {w['name']} ({w['address'][:12]}...)")
    choice = Prompt.ask("Select to remove (0=cancel)", default="0")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(whales):
            remove_whale(whales[idx]["address"])
            console.print(f"[green]Removed.[/green]")
    except (ValueError, IndexError):
        pass


async def deployer_check_mode():
    print_banner()
    from rich.prompt import Prompt

    address = Prompt.ask("[cyan]Paste token address to check deployer[/cyan]").strip()
    if not address:
        return

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Checking deployer history...", total=None)
        result = await analyze_token_deployer(address)

    if not result.get("found"):
        console.print("[red]Could not determine token creator.[/red]")
        return

    stats = result.get("stats", {})
    creator = result.get("creator", "?")
    status = stats.get("status", "?")

    color = {"trusted": "green", "suspicious": "red", "unknown": "yellow"}.get(status, "white")

    console.print(f"\n[bold]Creator Wallet:[/bold] [dim]{creator}[/dim]")
    console.print(f"Status: [{color}]{status.upper()}[/{color}]")
    console.print(f"Tokens deployed: {stats.get('total_tokens_found', '?')}")
    console.print(f"Checked: {stats.get('tokens_checked', 0)} | Successful: {stats.get('successful', 0)} | Rug: {stats.get('rug_count', 0)}")
    console.print(f"Success rate: {stats.get('success_rate', 0):.0f}% | Rug rate: {stats.get('rug_rate', 0):.0f}%")


async def deployer_list_mode():
    print_banner()
    deployers = load_deployer_list()

    if not deployers:
        console.print("[dim]No deployers tracked. Add via 'Add Deployer' menu.[/dim]")
        return

    console.print(f"[bold cyan]Tracked Deployers[/bold cyan] ({len(deployers)})\n")

    table = Table(title="", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold", width=18)
    table.add_column("Address", width=14)
    table.add_column("Tokens", justify="center", width=7)
    table.add_column("Last Scan", width=12)

    for d in deployers:
        table.add_row(
            d.get("name", "?")[:17],
            d.get("address", "?")[:12] + "...",
            str(d.get("total_deployed", "?")),
            (d.get("last_scanned") or "never")[:10],
        )

    console.print(table)


async def add_deployer_mode():
    print_banner()
    from rich.prompt import Prompt

    address = Prompt.ask("[cyan]Paste deployer wallet address[/cyan]").strip()
    if not address:
        return
    name = Prompt.ask("[cyan]Nickname (optional)[/cyan]", default="").strip()

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Fetching deployer stats...", total=None)
        from core.deployer_check import get_deployer_stats
        stats = await get_deployer_stats(address)

    result = add_deployer(address, name)
    console.print(f"\n[green]Deployer added: {result['name']}[/green]")
    console.print(f"  Success rate: {stats.get('success_rate', 0):.0f}% | Rug count: {stats.get('rug_count', 0)} | Status: {stats.get('status', 'unknown')}")


async def remove_deployer_mode():
    print_banner()
    from rich.prompt import Prompt

    deployers = load_deployer_list()
    if not deployers:
        console.print("[dim]No deployers tracked.[/dim]")
        return

    for i, d in enumerate(deployers, 1):
        console.print(f"  [{i}] {d.get('name', '?')} ({d.get('address', '?')[:12]}...)")

    choice = Prompt.ask("Select to remove (0=cancel)", default="0")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(deployers):
            remove_deployer(deployers[idx]["address"])
            console.print(f"[green]Removed.[/green]")
    except (ValueError, IndexError):
        pass


async def whale_portfolio_view():
    print_banner()
    console.print("[bold cyan]Whale Portfolio[/bold cyan]\n")
    console.print("[dim]Scanning token holdings for all tracked whales...[/dim]\n")

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Fetching whale portfolios...", total=None)
        portfolios = await scan_whale_portfolios()

    if not portfolios:
        console.print("[dim]No whale portfolios found or no whales tracked.[/dim]")
        return

    for p in portfolios:
        console.print(f"\n[bold cyan]🐋 {p['name']}[/bold cyan] ({p['total_tokens']} tokens)")
        console.print(f"   [dim]{p['wallet'][:12]}...[/dim]")

        if not p.get("holdings"):
            console.print("   [dim]No token holdings found[/dim]")
            continue

        table = Table(title="", box=box.SIMPLE, show_header=True, header_style="dim")
        table.add_column("Mint", width=14, style="dim")
        table.add_column("Amount", justify="right", width=12)

        for h in p["holdings"][:10]:
            table.add_row(
                str(h.get("mint", ""))[:12] + "..." if len(str(h.get("mint", ""))) > 12 else str(h.get("mint", "")),
                f"{h.get('ui_amount', 0):,.4f}",
            )
        console.print(table)


async def smart_money_mode():
    print_banner()
    from rich.prompt import Prompt

    console.print("[bold cyan]Smart Money / Insider Tracker[/bold cyan]\n")
    console.print(f"[dim]Learned smart wallets tracked: {len(load_smart_wallets())}[/dim]\n")

    choice = Prompt.ask("Mode", choices=["analyze", "add", "remove", "list"], default="analyze")
    whales = load_smart_wallets()

    if choice == "add":
        address = Prompt.ask("[cyan]Smart wallet address[/cyan]").strip()
        if address:
            name = Prompt.ask("[cyan]Nickname (optional)[/cyan]", default="").strip()
            rec = add_smart_wallet(address, name)
            console.print(f"[green]Smart wallet added: {rec['name']}[/green]")
        return
    elif choice == "remove":
        if not whales:
            console.print("[dim]No smart wallets tracked.[/dim]")
            return
        for i, w in enumerate(whales, 1):
            console.print(f"  [{i}] {w['name']} ({w['address'][:12]}...) hits:{w.get('hit_count', 0)}")
        sel = Prompt.ask("Select to remove (0=cancel)", default="0")
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(whales):
                remove_smart_wallet(whales[idx]["address"])
                console.print("[green]Removed.[/green]")
        except (ValueError, IndexError):
            pass
        return
    elif choice == "list":
        if not whales:
            console.print("[dim]No smart wallets tracked yet. They are auto-learned from winning signals.[/dim]")
            return
        table = Table(title="", box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold", width=18)
        table.add_column("Address", width=14)
        table.add_column("Hits", justify="center", width=6)
        table.add_column("PnL%", justify="right", width=8)
        table.add_column("Source", width=10)
        for w in whales:
            table.add_row(
                w.get("name", "?")[:17],
                w.get("address", "?")[:12] + "...",
                str(w.get("hit_count", 0)),
                f"{w.get('realized_pnl_pct', 0):.0f}",
                w.get("source", "?"),
            )
        console.print(table)
        return

    address = Prompt.ask("[cyan]Paste token address[/cyan]").strip()
    if not address:
        return

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Fetching token data...", total=None)
        info = await get_token_info(address)

    if not info:
        console.print(f"[red]Token tidak ditemukan: {address}[/red]")
        return

    with Progress(SpinnerColumn(spinner_name="line"), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("[cyan]Analyzing smart money...", total=None)
        result = await analyze_token(info)
        sm = await analyze_smart_money(address)

    console.clear()
    print_banner()
    print_token_detail(result)

    if not sm.get("found"):
        console.print("[dim]Smart money data unavailable.[/dim]")
        return

    console.print("\n[bold magenta]SMART MONEY ANALYSIS[/bold magenta]")
    color = {"high": "red", "medium": "yellow", "low": "green", "unknown": "white"}.get(sm.get("risk"), "white")
    console.print(f"  Risk: [{color}]{sm.get('risk', '?').upper()}[/{color}] | Signal: {sm.get('signal', '?')} | Adj: {sm.get('score_adjustment', 0)}")
    console.print(f"  Known smart holders: {sm.get('smart_holder_count', 0)}")
    if sm.get("early_buyer_retention_pct") is not None:
        console.print(f"  Early-buyer retention: {sm['early_buyer_retention_pct']}%")
    if sm.get("insider_selling"):
        console.print("  [red]⚠ INSIDER SELLING DETECTED — early buyers cashing out[/red]")
    for h in sm.get("smart_holders", [])[:10]:
        console.print(f"    {h['name']} ({h['wallet'][:12]}...) amount:{h['amount']:.2f} hits:{h.get('hit_count', 0)}")


async def narratives_mode():
    print_banner()
    console.print("[bold cyan]Narrative / Sector Momentum[/bold cyan]\n")
    console.print("[dim]Running quick scan to rank sectors by momentum...[/dim]\n")

    results = await quick_scan()
    if not results:
        return

    for r in results:
        r["narratives"] = r.get("narratives") or classify_narrative(r.get("name", ""), r.get("symbol", ""))

    sectors = track_sector_momentum(results)
    _print_sectors(sectors)


def _print_sectors(sectors):
    if not sectors:
        console.print("[dim]No sector data.[/dim]")
        return

    table = Table(title="", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Narrative", style="bold", width=14)
    table.add_column("Tokens", justify="center", width=8)
    table.add_column("Volume 24h", justify="right", width=14)
    table.add_column("Avg Chg%", justify="right", width=10)
    table.add_column("Avg Score", justify="right", width=10)
    table.add_column("Vol Δ", justify="right", width=12)

    for s in sectors:
        vold = s.get("volume_delta", 0)
        vold_str = f"[green]+${vold:,.0f}[/green]" if vold > 0 else f"[red]-${abs(vold):,.0f}[/red]" if vold < 0 else "-"
        chg = s.get("avg_change_24h", 0)
        chg_str = f"[green]+{chg:.1f}%[/green]" if chg > 0 else f"[red]{chg:.1f}%[/red]" if chg < 0 else "-"
        table.add_row(
            s["narrative"],
            str(s["token_count"]),
            f"${s['volume_24h']:,.0f}",
            chg_str,
            f"{s['avg_score']:.0f}",
            vold_str,
        )
    console.print(table)
    console.print("\n[dim]Sectors ranked by 24h volume. Use /narratives in Telegram.[/dim]")


def show_menu():
    print_banner()
    console.print("[1] [bold cyan]Live Scan[/bold cyan]      — Real-time monitoring new Solana pairs")
    console.print("[2] [bold cyan]Quick Scan[/bold cyan]     — One-time scan trending tokens")
    console.print("[20] [bold cyan]Deep Scan[/bold cyan]      — 50+ coins from 4 sources + charts")
    console.print("[3] [bold cyan]Pump.fun Scan[/bold cyan]  — Scan recent Pump.fun launches")
    console.print("[4] [bold cyan]Export Data[/bold cyan]     — Quick scan + export CSV/JSON")
    console.print("[5] [bold cyan]Config[/bold cyan]          — Set Telegram bot credentials")
    console.print("[6] [bold cyan]Detect Chat[/bold cyan]      — Auto-detect Telegram chat ID")
    console.print("[7] [bold cyan]Telegram Bot[/bold cyan]     — Start bot listener (responds to commands)")
    console.print("[8] [bold cyan]Analyze Token[/bold cyan]    — Analyze token by address")
    console.print("[9] [bold cyan]Filter Scan[/bold cyan]       — Custom filter + multi-query deep scan")
    console.print("[10] [bold cyan]Watchlist[/bold cyan]         — View tracked tokens")
    console.print("[11] [bold cyan]+ Watchlist[/bold cyan]       — Add token to watchlist")
    console.print("[12] [bold cyan]- Watchlist[/bold cyan]       — Remove from watchlist")
    console.print("[13] [bold cyan]Whales[/bold cyan]           — Scan whale wallets for buys")
    console.print("[14] [bold cyan]+ Whale[/bold cyan]          — Add whale wallet to track")
    console.print("[15] [bold cyan]- Whale[/bold cyan]          — Remove whale wallet")
    console.print("[19] [bold cyan]Whale Portfolio[/bold cyan]  — View all tracked whale holdings")
    console.print("[16] [bold cyan]Deployer[/bold cyan]        — Check token deployer history")
    console.print("[17] [bold cyan]Deployers[/bold cyan]       — View tracked deployers")
    console.print("[18] [bold cyan]+ Deployer[/bold cyan]      — Add deployer wallet to track")
    console.print("[21] [bold cyan]Smart Money[/bold cyan]     — Analyze smart money & insider selling")
    console.print("[22] [bold cyan]Narratives[/bold cyan]      — Sector momentum ranking")
    console.print("[0] [bold red]Exit[/bold red]")
    console.print()


async def main():
    signal.signal(signal.SIGINT, signal_handler)

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        show_menu()
        mode = Prompt.ask("Select mode", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22"], default="2")

    mode_map = {
        "1": live_scan,
        "2": quick_scan,
        "20": deep_scan_mode,
        "3": pumpfun_scan,
        "4": run_export,
        "5": config_wizard,
        "6": start_chat_listener,
        "7": run_telegram_bot,
        "8": analyze_by_address,
        "9": custom_filter_scan,
        "10": view_watchlist,
        "11": add_to_watchlist_mode,
        "12": remove_watchlist_mode,
        "13": whale_scan,
        "14": add_whale_mode,
        "15": remove_whale_mode,
        "16": deployer_check_mode,
        "17": deployer_list_mode,
        "18": add_deployer_mode,
        "19": whale_portfolio_view,
        "21": smart_money_mode,
        "22": narratives_mode,
    }

    if mode == "0":
        console.print("[dim]Exiting...[/dim]")
        return

    try:
        if mode in mode_map:
            await mode_map[mode]()
    finally:
        try:
            client = await HttpClient.get_instance()
            await client.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
