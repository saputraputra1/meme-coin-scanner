from typing import Dict
from config import HELIUS_API_KEY
from core.solscan import analyze_holders


async def analyze_holder_distribution(token_address: str) -> Dict:
    data = await analyze_holders(token_address)

    if data["total_holders"] == 0:
        data = await _analyze_holders_helius(token_address)

    score = 0
    total = data["total_holders"]
    top10_pct = data["top10_pct"]

    if isinstance(total, (int, float)) and total == 0:
        data_available = False
        score = 0
        total = "?"
        top10_pct = "?"
    else:
        data_available = True

    if data_available:
        if total >= 200:
            score += 40
        elif total >= 100:
            score += 30
        elif total >= 50:
            score += 15
        else:
            score += 10

        if top10_pct <= 15:
            score += 40
        elif top10_pct <= 30:
            score += 30
        elif top10_pct <= 50:
            score += 15
        elif top10_pct <= 70:
            score += 5
        else:
            score += 0

        if total >= 100 and top10_pct <= 30:
            score += 20

    risk = "low" if score >= 70 else "medium" if score >= 40 else "high"

    health = "EXCELLENT" if score >= 80 and isinstance(top10_pct, (int, float)) and top10_pct <= 15 else \
             "GOOD" if score >= 50 else \
             "FAIR" if score >= 35 else \
             "POOR"

    bar_chars = 10
    if isinstance(top10_pct, (int, float)):
        filled = int((top10_pct / 100) * bar_chars)
        bar = "|" + "█" * filled + "░" * (bar_chars - filled) + "|"
    else:
        bar = "|" + "?" * bar_chars + "|"

    return {
        "score": score,
        "total_holders": total,
        "top10_concentration_pct": top10_pct,
        "data_available": data_available,
        "risk": risk,
        "health": health,
        "distribution_bar": bar,
    }


async def _analyze_holders_helius(token_address: str) -> Dict:
    from core.helius import HeliusClient

    client = HeliusClient(HELIUS_API_KEY)
    try:
        holders = await client.get_token_largest_holders(token_address, limit=20)
        if not holders:
            return {"total_holders": 0, "top10_pct": 100, "top10_count": 0, "is_concentrated": True, "risk": "high"}

        total_held = sum(h["ui_amount"] for h in holders)
        if total_held == 0:
            total_held = 1

        top10_amount = sum(h["ui_amount"] for h in holders[:10])
        top10_pct = (top10_amount / total_held) * 100

        risk = "low" if top10_pct < 30 else "medium" if top10_pct < 60 else "high"

        return {
            "total_holders": len(holders),
            "top10_pct": round(top10_pct, 2),
            "top10_count": min(10, len(holders)),
            "is_concentrated": top10_pct > 50,
            "risk": risk,
        }
    except Exception:
        return {"total_holders": 0, "top10_pct": 100, "top10_count": 0, "is_concentrated": True, "risk": "high"}
    finally:
        await client.close()
