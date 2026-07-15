import asyncio
import logging
from typing import Dict
from config import HELIUS_API_KEY
from core.solscan import analyze_holders

logger = logging.getLogger("memecoin-bot")


async def analyze_holder_distribution(token_address: str) -> Dict:
    data = None
    sources_tried = []

    try:
        data = await asyncio.wait_for(_analyze_holders_helius(token_address), timeout=15)
        sources_tried.append("helius")
    except Exception as e:
        logger.warning(f"Helius holder fetch failed for {token_address[:8]}: {e}")

    if data is None or data["total_holders"] == 0:
        try:
            data = await asyncio.wait_for(analyze_holders(token_address), timeout=10)
            sources_tried.append("solscan")
        except Exception as e:
            logger.warning(f"Solscan holder fallback failed for {token_address[:8]}: {e}")

    if data is None:
        logger.error(f"All holder sources failed for {token_address[:8]}")
        data = {"total_holders": 0, "top10_pct": 100, "top10_count": 0, "is_concentrated": True, "risk": "high", "top_holders": []}

    logger.info(f"Holder data for {token_address[:8]}: source={'+'.join(sources_tried)} total={data.get('total_holders')} top10={data.get('top10_pct')}% top_holders={len(data.get('top_holders', []))}")

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
        "top_holders": data.get("top_holders", []),
    }


async def _analyze_holders_helius(token_address: str) -> Dict:
    from core.helius import HeliusClient

    client = HeliusClient(HELIUS_API_KEY)
    try:
        holders = await client.get_token_largest_holders(token_address, limit=20)
        if not holders:
            logger.warning(f"Helius returned no holders for {token_address[:8]}")
            return {"total_holders": 0, "top10_pct": 100, "top10_count": 0, "is_concentrated": True, "risk": "high", "top_holders": []}

        supply_data = await client.get_token_supply(token_address)
        if supply_data:
            total_supply = supply_data.get("ui_amount", 0) or 1
        else:
            total_supply = sum(h["ui_amount"] for h in holders) or 1

        top10_amount = sum(h["ui_amount"] for h in holders[:10])
        top10_pct = (top10_amount / total_supply) * 100

        risk = "low" if top10_pct < 30 else "medium" if top10_pct < 60 else "high"

        top_holders = []
        for h in holders[:10]:
            pct = (h["ui_amount"] / total_supply) * 100 if total_supply > 0 else 0
            top_holders.append({
                "address": h.get("address", "unknown"),
                "pct": round(pct, 2),
                "amount": h.get("ui_amount", 0),
            })

        logger.info(f"Helius holder data: total_supply={total_supply:.2f} top10_pct={top10_pct:.2f}% holders={len(holders)}")

        return {
            "total_holders": len(holders),
            "top10_pct": round(top10_pct, 2),
            "top10_count": min(10, len(holders)),
            "is_concentrated": top10_pct > 50,
            "risk": risk,
            "top_holders": top_holders,
        }
    except Exception as e:
        logger.error(f"Helius holder error for {token_address[:8]}: {e}")
        return {"total_holders": 0, "top10_pct": 100, "top10_count": 0, "is_concentrated": True, "risk": "high", "top_holders": []}
    finally:
        await client.close()
