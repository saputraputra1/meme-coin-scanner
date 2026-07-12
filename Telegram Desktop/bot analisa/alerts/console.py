from typing import List, Dict
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich import box

console = Console()


def get_verdict_color(verdict: str) -> str:
    return {"HOT": "bold red", "POTENTIAL": "green", "WATCH": "yellow", "CAUTION": "dim"}.get(verdict, "white")


def get_signal_color(signal: str) -> str:
    return {"STRONG_BUY": "bold green", "BUY": "green", "WATCH": "yellow", "AVOID": "bold red"}.get(signal, "white")


def get_signal_emoji(signal: str) -> str:
    return {"STRONG_BUY": "🔥 BUY", "BUY": "🟢 BUY", "WATCH": "🟡 WATCH", "AVOID": "🔴 SKIP"}.get(signal, signal)


def get_score_color(score: int) -> str:
    if score >= 85:
        return "bold red"
    if score >= 70:
        return "green"
    if score >= 40:
        return "yellow"
    return "dim"


def print_banner():
    console.print()
    console.print(Panel.fit(
        "[bold cyan]MEME COIN SCANNER - SOLANA[/bold cyan]\n"
        "[dim]Professional Analysis | Safety | Holders | Signal[/dim]",
        border_style="cyan",
    ))


def build_results_table(results: List[Dict]) -> Table:
    table = Table(
        title=f"\n[bold]Results — {datetime.now().strftime('%H:%M:%S')}[/bold]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("#", style="dim", width=3)
    table.add_column("Token", style="bold", width=14)
    table.add_column("Signal", width=10)
    table.add_column("Score", justify="center", width=6)
    table.add_column("24h%", justify="right", width=7)
    table.add_column("MCap", justify="right", width=9)
    table.add_column("Liq", justify="right", width=8)
    table.add_column("Hold", justify="center", width=5)
    table.add_column("🐋", justify="center", width=4)
    table.add_column("Age", justify="right", width=5)

    if not results:
        table.add_row("—", "No tokens found", "", "", "", "", "", "", "", "")
        return table

    for i, r in enumerate(results, 1):
        score = r.get("score", {}).get("total_score", 0)
        mcap = r.get("market_cap", 0)
        liq = r.get("liquidity_usd", 0)
        holders = r.get("score", {}).get("details", {}).get("holders", {}).get("total_holders", "?")
        age_val = r.get("age_minutes", "?")
        price_change = r.get("price_change_24h", None)
        signal_data = r.get("professional", {})
        signal = signal_data.get("signal", "BUY")
        signal_label = get_signal_emoji(signal)
        sig_color = get_signal_color(signal)

        whale_holders = r.get("whale_holders", [])
        whale_str = f"[cyan]{len(whale_holders)}[/cyan]" if whale_holders else "-"

        score_style = get_score_color(score)

        if isinstance(price_change, (int, float)):
            pc_style = "green" if price_change > 0 else "red"
            pc_str = f"[{pc_style}]{price_change:+.0f}%[/{pc_style}]"
        else:
            pc_str = "-"

        table.add_row(
            str(i),
            r.get("symbol", "???"),
            f"[{sig_color}]{signal_label}[/{sig_color}]",
            f"[{score_style}]{score}[/{score_style}]",
            pc_str,
            f"${mcap:,.0f}" if isinstance(mcap, (int, float)) else "$?",
            f"${liq:,.0f}" if isinstance(liq, (int, float)) else "$?",
            str(holders),
            whale_str,
            f"{age_val:.0f}m" if isinstance(age_val, (int, float)) else "?",
        )

    return table


def print_token_detail(result: Dict):
    from analyzers.professional import build_holder_bar, holder_health_label

    score = result.get("score", {})
    breakdown = score.get("breakdown", {})
    details = score.get("details", {})
    safety = details.get("safety", {})
    safety_checks = safety.get("checks", {})
    liquidity = details.get("liquidity", {})
    holders = details.get("holders", {})
    social = details.get("social", {})
    pro = result.get("professional", {})
    deployer = result.get("deployer_check", {}).get("stats", {})
    bundler = result.get("bundler_check", {})

    signal = pro.get("signal", "BUY")
    signal_label = pro.get("signal_label", signal)
    confidence = pro.get("confidence", "?")
    position = pro.get("position_recommendation", "N/A")
    concerns = pro.get("concerns", [])
    positives = pro.get("positives", [])
    summary = pro.get("summary", "")

    sig_color = get_signal_color(signal)
    sig_emoji = get_signal_emoji(signal)

    mint = safety_checks.get("mint_authority", "?")
    freeze = safety_checks.get("freeze_authority", "?")
    verified = safety_checks.get("verified", "?")
    honeypot = safety_checks.get("honeypot_detected", "?")
    can_swap = safety_checks.get("can_swap", "?")
    market_type = safety_checks.get("market_type", "?")
    mint_icon = "✅" if mint is True else "❌" if mint is False else "❓"
    freeze_icon = "✅" if freeze is True else "❌" if freeze is False else "❓"
    hp_icon = "🛑" if honeypot is True else "✅" if honeypot is False else "❓"
    swap_icon = "✅" if can_swap is True else "❌" if can_swap is False else "❓"

    holder_total = holders.get("total_holders", "?")
    top10 = holders.get("top10_concentration_pct", "?")
    holder_health = holders.get("health", "?")
    bar = holders.get("distribution_bar", "|???|")
    deployer_rug = deployer.get("rug_count", 0)
    deployer_success = deployer.get("success_rate", 0)
    deployer_status = deployer.get("status", "unknown")
    bundler_count = bundler.get("rapid_buys_under_60s", 0) if bundler else 0

    console.print()
    header = f"[bold cyan]{result.get('symbol', '???')} — {result.get('name', 'Unknown')}\n"
    header += f"[{sig_color}]{sig_emoji} | Score: {score.get('total_score', 0)}/100 | Confidence: {confidence}/10 | {position}[/{sig_color}]\n"
    header += f"[dim]{result.get('token_address', '')}[/dim]"
    console.print(Panel(header, border_style=sig_color.replace("bold ", "")))

    price = result.get("price_usd", 0)
    mcap = liquidity.get("market_cap", 0)
    liq = liquidity.get("liquidity_usd", 0)
    vol = result.get("volume_24h", 0)
    price_ch = result.get("price_change_24h", 0) or 0
    age_val = result.get("age_minutes", "?")

    console.print(f"  💰 Price: ${price:.8f} | MCap: ${mcap:,.0f} | 24h: ", end="")
    if isinstance(price_ch, (int, float)):
        pc_style = "green" if price_ch > 0 else "red"
        console.print(f"[{pc_style}]{price_ch:+.0f}%[/{pc_style}]", end="")
    console.print(f" | Vol: ${vol:,.0f}")

    console.print(f"\n  [bold]SECURITY[/bold] [{safety.get('score', '?')}/100]")
    console.print(f"    Mint: {mint_icon} | Freeze: {freeze_icon} | Verified: {'✅' if verified else '❌'}")
    console.print(f"    Honeypot: {hp_icon} | Swap: {swap_icon} | Market: {market_type}")

    rugcheck_risks = safety_checks.get("risk_items", [])
    if rugcheck_risks:
        console.print(f"    [red]Risks:[/red] {', '.join(rugcheck_risks[:2])}")

    console.print(f"\n  [bold]DISTRIBUTION[/bold] [{holder_health}]")
    if isinstance(top10, (int, float)):
        console.print(f"    Top10 holders: {top10:.0f}% {bar}")
    else:
        console.print(f"    Holders: {holder_total} | {bar}")
    console.print(f"    Count: {holder_total} | Health: {holder_health}")

    if bundler and bundler_count > 0:
        console.print(f"    [red]Bundler: {bundler_count} rapid buys first 60s ({bundler.get('unique_buyers_first_5min', 0)} wallets)[/red]")

    dep_color = {"trusted": "green", "suspicious": "red", "unknown": "yellow"}.get(deployer_status, "white")
    console.print(f"\n  [bold]DEPLOYER[/bold] [{dep_color}]{deployer_status.upper()}[/{dep_color}]")
    if deployer_success:
        console.print(f"    Success rate: {deployer_success:.0f}% | Rug count: {deployer_rug}")

    console.print(f"\n  [bold]SOCIAL[/bold] {', '.join(social.get('links', [])) or 'none'} | Twitter: {social.get('twitter_handle', 'none')}")

    console.print(f"\n  [bold]LIQUIDITY[/bold] ${liq:,.0f} | Liq/MCap: {liq/max(mcap,1)*100:.0f}%")

    whale_holders = result.get("whale_holders", [])
    if whale_holders:
        console.print(f"\n  [bold cyan]TRACKED WHALES[/bold cyan] ({len(whale_holders)} tracked)")
        for wh in whale_holders[:5]:
            console.print(f"    🐋 {wh['name']}: {wh.get('amount', 0):,.0f} tokens | {wh['wallet'][:8]}...")

    auto_whales = result.get("auto_whales", {})
    if auto_whales.get("found"):
        awh = auto_whales
        risk_label = awh.get("concentration_risk", "?")
        risk_color = "green" if risk_label == "low" else "yellow" if risk_label == "medium" else "red"
        console.print(f"\n  [bold cyan]WHALES (auto-detected)[/bold cyan] | Supply: [{risk_color}]{awh['total_whale_supply_pct']:.1f}%[/{risk_color}] | Risk: [{risk_color}]{risk_label}[/{risk_color}]")
        for w in awh.get("whales", [])[:3]:
            sol = f" | {w['sol_balance']:,.0f} SOL" if w.get('sol_balance') else ""
            console.print(f"    🐋 {w['wallet_short']}: {w['supply_pct']:.1f}%{sol}")
        for d in awh.get("dolphins", [])[:2]:
            console.print(f"    🐬 {d['wallet_short']}: {d['supply_pct']:.1f}%")
        if awh.get("whale_count", 0) + awh.get("dolphin_count", 0) > 5:
            console.print(f"    [dim]... and {awh['whale_count'] + awh['dolphin_count'] - 5} more wallets[/dim]")
    if positives:
        console.print(f"    [green]✓ {', '.join(positives[:4])}[/green]")
    if concerns:
        console.print(f"    [red]✗ {', '.join(concerns[:4])}[/red]")

    console.print(f"\n  [bold cyan]VERDICT: [{sig_color}]{signal_label}[/{sig_color}][/bold cyan]")
    console.print(f"  [dim]{summary}[/dim]")
    console.print(f"  [dim]Position: {position} | Confidence: {confidence}/10[/dim]")

    charts = result.get("charts", {})
    if charts:
        console.print(f"\n  [bold]CHARTS:[/bold]")
        if charts.get("price_chart"):
            console.print(f"  [dim][link={charts['price_chart']}]Price Chart (PNG)[/link][/dim]")
        if charts.get("score_chart"):
            console.print(f"  [dim][link={charts['score_chart']}]Score Breakdown (PNG)[/link][/dim]")

    console.print(f"\n  [dim][link={result.get('url', '')}]View on DexScreener[/link][/dim]")
