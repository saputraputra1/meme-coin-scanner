from typing import Dict, Optional
from utils.client import HttpClient

JUPITER_QUOTE = "https://quote-api.jup.ag/v6/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


async def simulate_swap(
    token_address: str,
    input_mint: str = SOL_MINT,
    amount: int = 5000000,
    slippage_bps: int = 500,
) -> Dict:
    client = await HttpClient.get_instance()

    params = {
        "inputMint": input_mint,
        "outputMint": token_address,
        "amount": str(amount),
        "slippageBps": slippage_bps,
    }

    try:
        data = await client.get(JUPITER_QUOTE, params=params)
        if not data or "error" in data:
            return _failed_swap("No route found (low liquidity or honeypot)")
    except Exception as e:
        return _failed_swap(f"Quote failed: {str(e)[:80]}")

    routes = data.get("routePlan", data.get("data", []))
    if not routes and not data.get("outAmount"):
        return _failed_swap("No valid route")

    out_amount = int(data.get("outAmount", 0))
    in_amount = int(data.get("inAmount", 0))
    price_impact = float(data.get("priceImpactPct", 50) or 50)

    return {
        "success": True,
        "in_amount": in_amount,
        "out_amount": out_amount,
        "price_impact_pct": round(price_impact, 4),
        "can_swap": out_amount > 0,
        "is_healthy": price_impact < 30,
        "dexes": _parse_route(routes),
        "error": None,
    }


def _failed_swap(error: str) -> Dict:
    return {
        "success": False,
        "in_amount": 0,
        "out_amount": 0,
        "price_impact_pct": 100,
        "can_swap": False,
        "is_healthy": False,
        "dexes": [],
        "error": error,
    }


def _parse_route(routes: list) -> list:
    dexes = []
    if isinstance(routes, list):
        for r in routes:
            if isinstance(r, dict):
                dexes.append(r.get("swapInfo", {}).get("label", "unknown"))
    return dexes


async def swap_check_report(token_address: str) -> Dict:
    sol_swap = await simulate_swap(token_address, SOL_MINT, 5000000)
    usdc_swap = await simulate_swap(token_address, USDC_MINT, 10000000)

    can_sell = sol_swap.get("can_swap", False) or usdc_swap.get("can_swap", False)

    if sol_swap.get("success") and usdc_swap.get("success"):
        worst_impact = max(sol_swap.get("price_impact_pct", 100), usdc_swap.get("price_impact_pct", 100))
    elif sol_swap.get("success"):
        worst_impact = sol_swap.get("price_impact_pct", 100)
    elif usdc_swap.get("success"):
        worst_impact = usdc_swap.get("price_impact_pct", 100)
    else:
        worst_impact = 100

    is_suspicious = (not can_sell) or worst_impact >= 90

    score = 100 if can_sell and worst_impact < 5 else 70 if can_sell and worst_impact < 15 else 40 if can_sell else 0

    return {
        "can_swap": can_sell,
        "price_impact_pct": round(worst_impact, 2),
        "is_suspicious": is_suspicious,
        "score": score,
        "sol_route": sol_swap.get("dexes", []),
        "usdc_route": usdc_swap.get("dexes", []),
        "error": sol_swap.get("error") and usdc_swap.get("error") and "No routes available",
    }
