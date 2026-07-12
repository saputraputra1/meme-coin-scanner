from typing import Dict, List
from config import HELIUS_API_KEY
from core.helius import HeliusClient


async def detect_whales_for_token(token_address: str, max_holders: int = 30) -> Dict:
    client = HeliusClient(HELIUS_API_KEY)

    try:
        holders = await client.get_token_largest_holders(token_address, limit=max_holders)
    except Exception:
        return _empty_result()

    if not holders:
        await client.close()
        return _empty_result()

    total_supply = sum(h.get("ui_amount", 0) for h in holders)
    if total_supply == 0:
        await client.close()
        return _empty_result()

    whales = []
    dolphin = []
    fish = []
    total_whale_pct = 0

    for h in holders:
        ui_amount = h.get("ui_amount", 0)
        pct = (ui_amount / total_supply * 100) if total_supply > 0 else 0

        sol_balance = None
        try:
            sol_balance = await client.get_balance(h["address"])
        except Exception:
            pass

        classification = "WHALE" if pct >= 2 else "DOLPHIN" if pct >= 0.5 else "FISH"
        wallet_short = str(h.get("address", ""))[:8] + "..." if len(str(h.get("address", ""))) > 8 else h.get("address", "")

        entry = {
            "wallet": str(h.get("address", "")),
            "wallet_short": wallet_short,
            "amount": ui_amount,
            "supply_pct": round(pct, 2),
            "sol_balance": round(sol_balance, 2) if sol_balance else None,
            "classification": classification,
        }

        if classification == "WHALE":
            whales.append(entry)
            total_whale_pct += pct
        elif classification == "DOLPHIN":
            dolphin.append(entry)
            total_whale_pct += pct
        else:
            fish.append(entry)

        if len(whales) + len(dolphin) >= 15:
            break

    await client.close()

    all_classified = whales + dolphin
    top5_pct = sum(h["supply_pct"] for h in all_classified[:5]) if all_classified else 0

    total_whale_pct = round(total_whale_pct, 2)

    risk = "low"
    if total_whale_pct > 30:
        risk = "high"
    elif total_whale_pct > 15:
        risk = "medium"

    return {
        "found": True,
        "total_holders_checked": len(holders),
        "whales": whales,
        "dolphins": dolphin,
        "fish_count": len(fish),
        "total_whale_supply_pct": total_whale_pct,
        "top5_supply_pct": round(top5_pct, 2),
        "whale_count": len(whales),
        "dolphin_count": len(dolphin),
        "total_supply": total_supply,
        "concentration_risk": risk,
    }


def _empty_result() -> Dict:
    return {
        "found": False,
        "total_holders_checked": 0,
        "whales": [],
        "dolphins": [],
        "fish_count": 0,
        "total_whale_supply_pct": 0,
        "top5_supply_pct": 0,
        "whale_count": 0,
        "dolphin_count": 0,
        "total_supply": 0,
        "concentration_risk": "unknown",
    }
