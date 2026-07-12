from typing import Dict
from utils.client import HttpClient

SOL_MINT = "So11111111111111111111111111111111111111112"


async def get_market_context() -> Dict:
    client = await HttpClient.get_instance()

    sol_price = 0
    sol_change_24h = 0
    sol_change_1h = 0
    market_mood = "neutral"

    try:
        data = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{SOL_MINT}")
        pairs = data.get("pairs", []) if data else []
        solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        if solana_pairs:
            sol_pair = solana_pairs[0]
            sol_price = float(sol_pair.get("priceUsd", 0) or 0)
            pc = sol_pair.get("priceChange", {})
            sol_change_24h = float(pc.get("h24", 0) or 0)
            sol_change_1h = float(pc.get("h1", 0) or 0)
    except Exception:
        pass

    if sol_change_24h > 5 and sol_change_1h > 2:
        market_mood = "very_bullish"
    elif sol_change_24h > 2 and sol_change_1h > 0:
        market_mood = "bullish"
    elif sol_change_24h < -5 and sol_change_1h < -2:
        market_mood = "very_bearish"
    elif sol_change_24h < -2 and sol_change_1h < 0:
        market_mood = "bearish"
    else:
        market_mood = "neutral"

    meme_friendly = market_mood in ("bullish", "very_bullish") or sol_change_1h > 1

    return {
        "sol_price": sol_price,
        "sol_change_24h": sol_change_24h,
        "sol_change_1h": sol_change_1h,
        "market_mood": market_mood,
        "meme_friendly": meme_friendly,
    }


def get_market_adjustment(context: Dict) -> int:
    mood = context.get("market_mood", "neutral")
    if mood == "very_bullish":
        return 2
    elif mood == "bullish":
        return 1
    elif mood == "very_bearish":
        return -2
    elif mood == "bearish":
        return -1
    return 0


def get_market_summary(context: Dict) -> str:
    mood = context.get("market_mood", "neutral")
    sol = context.get("sol_price", 0)
    change = context.get("sol_change_24h", 0)

    emoji_map = {
        "very_bullish": "🚀",
        "bullish": "📈",
        "neutral": "➡️",
        "bearish": "📉",
        "very_bearish": "💀",
    }
    emoji = emoji_map.get(mood, "❓")

    return f"{emoji} SOL ${sol:,.0f} ({change:+.0f}%) | Market: {mood.upper()}"
