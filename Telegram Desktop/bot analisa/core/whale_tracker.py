import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from config import HELIUS_API_KEY
from core.helius import HeliusClient

WHALE_FILE = Path(__file__).parent.parent / "data" / "known_whales.json"
WHALE_PORTFOLIO_FILE = Path(__file__).parent.parent / "data" / "whale_portfolio.json"

DEFAULT_WHALES = [
    {"address": "4hWp3n9k5GcRG5wvY2pXJvWGLFZbB6xqFhPzA8cN1pW7", "name": "Whale #1 (manual)", "note": "Add real whale addresses here"},
]

WSOL_MINT = "So11111111111111111111111111111111111111112"


def load_known_whales() -> List[Dict]:
    if WHALE_FILE.exists():
        try:
            whales = json.loads(WHALE_FILE.read_text())
            if whales:
                return whales
        except Exception:
            pass
    return DEFAULT_WHALES


def save_whales(whales: List[Dict]):
    WHALE_FILE.parent.mkdir(exist_ok=True, parents=True)
    WHALE_FILE.write_text(json.dumps(whales, indent=2, ensure_ascii=False))


def add_whale(address: str, name: str = "") -> Dict:
    whales = load_known_whales()
    for w in whales:
        if w["address"] == address:
            return w
    whale = {"address": address, "name": name or f"Whale {address[:8]}", "added": datetime.now(timezone.utc).isoformat()}
    whales.append(whale)
    save_whales(whales)
    return whale


def remove_whale(address: str) -> bool:
    whales = load_known_whales()
    new_whales = [w for w in whales if w["address"] != address]
    if len(new_whales) < len(whales):
        save_whales(new_whales)
        return True
    return False


def save_portfolio(portfolio: Dict[str, List[Dict]]):
    WHALE_PORTFOLIO_FILE.parent.mkdir(exist_ok=True, parents=True)
    WHALE_PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False, default=str))


def load_portfolio() -> Dict[str, List[Dict]]:
    if WHALE_PORTFOLIO_FILE.exists():
        try:
            return json.loads(WHALE_PORTFOLIO_FILE.read_text())
        except Exception:
            return {}
    return {}


async def scan_whale_portfolios() -> List[Dict]:
    whales = load_known_whales()
    active = [w for w in whales if w["address"] != DEFAULT_WHALES[0]["address"]]
    if not active:
        return []

    client = HeliusClient(HELIUS_API_KEY)
    portfolio_data = {}

    try:
        for whale in active:
            addr = whale["address"]
            accounts = await client.get_token_accounts(addr)

            holdings = []
            for acc in accounts[:15]:
                parsed = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = parsed.get("mint", "")
                ui_amount = parsed.get("tokenAmount", {}).get("uiAmount", 0) or 0
                amount = parsed.get("tokenAmount", {}).get("amount", "0")
                decimals = parsed.get("tokenAmount", {}).get("decimals", 0)

                if ui_amount > 0 and mint != WSOL_MINT:
                    holdings.append({
                        "mint": str(mint),
                        "amount": str(amount),
                        "ui_amount": float(ui_amount),
                        "decimals": int(decimals),
                    })

            holdings.sort(key=lambda x: x["ui_amount"], reverse=True)
            portfolio_data[addr] = holdings

        save_portfolio(portfolio_data)
    finally:
        await client.close()

    return _format_portfolio_display(whales, portfolio_data)


def _format_portfolio_display(whales: List[Dict], portfolio_data: Dict) -> List[Dict]:
    result = []
    for whale in whales:
        addr = whale["address"]
        holdings = portfolio_data.get(addr, [])
        result.append({
            "wallet": addr,
            "name": whale.get("name", addr[:8]),
            "added": whale.get("added", ""),
            "tokens_count": len(holdings),
            "holdings": holdings[:10],
            "total_tokens": len(holdings),
        })
    return result


async def scan_whale_buys(min_volume_sol: float = 0.1) -> List[Dict]:
    whales = load_known_whales()
    if not whales:
        return []

    client = HeliusClient(HELIUS_API_KEY)
    alerts = []

    try:
        for whale in whales[:5]:
            addr = whale["address"]
            if addr == DEFAULT_WHALES[0]["address"]:
                continue

            sigs = await client.get_signatures(addr, limit=10)
            for sig_info in sigs:
                sig = sig_info.get("signature", "")
                tx = await client.get_transaction(sig)
                if not tx:
                    continue

                buys = _extract_token_buys(tx, addr)
                block_time = sig_info.get("blockTime", 0)
                for buy in buys:
                    mint = buy.get("token", "")
                    symbol = _resolve_token_symbol(mint)
                    alerts.append({
                        "wallet": addr,
                        "wallet_name": whale.get("name", addr[:8]),
                        "token_mint": mint,
                        "token_symbol": symbol,
                        "token_amount": buy.get("token_amount", 0),
                        "amount_sol": buy.get("sol_amount", 0),
                        "signature": sig[:12] + "...",
                        "time": block_time,
                    })
    finally:
        await client.close()

    return alerts


async def check_whale_holds_token(token_address: str) -> List[Dict]:
    whales = load_known_whales()
    active = [w for w in whales if w["address"] != DEFAULT_WHALES[0]["address"]]
    if not active:
        return []

    client = HeliusClient(HELIUS_API_KEY)
    holders = []

    try:
        for whale in active:
            addr = whale["address"]
            balance = await client.get_token_balance(addr, token_address)
            if balance and balance.get("ui_amount", 0) > 0:
                holders.append({
                    "wallet": addr,
                    "name": whale.get("name", addr[:8]),
                    "amount": balance.get("ui_amount", 0),
                })
    finally:
        await client.close()

    return holders


TOKEN_SYMBOL_CACHE: Dict[str, str] = {}


def _resolve_token_symbol(mint: str) -> str:
    if mint in TOKEN_SYMBOL_CACHE:
        return TOKEN_SYMBOL_CACHE[mint]
    TOKEN_SYMBOL_CACHE[mint] = mint[:8] + "..."
    return TOKEN_SYMBOL_CACHE[mint]


def _extract_token_buys(tx_data: dict, whale_address: str) -> List[Dict]:
    buys = []
    meta = tx_data.get("meta", {})
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])

    for post in post_balances:
        mint = post.get("mint", "")
        owner = post.get("owner", "")
        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

        if owner != whale_address or post_amount == 0:
            continue

        pre_amount = 0
        for pre in pre_balances:
            if pre.get("mint") == mint and pre.get("owner") == owner:
                pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                break

        if post_amount > pre_amount:
            acct_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
            sol_change = 0
            for idx, bal in enumerate(meta.get("postBalances", [])):
                pre_bal = meta.get("preBalances", [])[idx] if idx < len(meta.get("preBalances", [])) else bal
                if idx < len(acct_keys) and acct_keys[idx] == whale_address:
                    sol_change = (float(pre_bal) - float(bal)) / 1e9
                    break

            buys.append({
                "token": mint,
                "token_amount": post_amount - pre_amount,
                "sol_amount": abs(sol_change) if sol_change else 0,
            })

    return buys
