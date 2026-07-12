from typing import Dict
from core.dexscreener import get_token_info


async def compare_tokens(address1: str, address2: str) -> Dict:
    info1 = await get_token_info(address1)
    info2 = await get_token_info(address2)

    if not info1 and not info2:
        return {"error": "Both tokens not found"}

    result = {"tokens": [], "winner": None, "comparison": {}}

    for i, (info, addr) in enumerate([(info1, address1), (info2, address2)]):
        if not info:
            continue

        bt = info.get("base_token", {})
        token = {
            "symbol": bt.get("symbol", "?"),
            "name": bt.get("name", "?"),
            "address": addr,
            "price_usd": info.get("price_usd", 0),
            "market_cap": info.get("market_cap", 0),
            "liquidity_usd": info.get("liquidity_usd", 0),
            "volume_24h": info.get("volume_24h", 0),
            "age_minutes": info.get("age_minutes", 0),
        }
        result["tokens"].append(token)

    if len(result["tokens"]) == 2:
        t1, t2 = result["tokens"]

        scores = {"token1": 0, "token2": 0}

        if t1["liquidity_usd"] > t2["liquidity_usd"] * 1.5:
            scores["token1"] += 1
        elif t2["liquidity_usd"] > t1["liquidity_usd"] * 1.5:
            scores["token2"] += 1

        if t1["market_cap"] < t2["market_cap"] and t1["market_cap"] < 100000:
            scores["token1"] += 1

        mc_ratio1 = t1["liquidity_usd"] / max(t1["market_cap"], 1) * 100
        mc_ratio2 = t2["liquidity_usd"] / max(t2["market_cap"], 1) * 100
        if mc_ratio1 > mc_ratio2 * 1.3:
            scores["token1"] += 1
        elif mc_ratio2 > mc_ratio1 * 1.3:
            scores["token2"] += 1

        vol_ratio1 = t1["volume_24h"] / max(t1["market_cap"], 1) if t1["market_cap"] > 0 else 0
        vol_ratio2 = t2["volume_24h"] / max(t2["market_cap"], 1) if t2["market_cap"] > 0 else 0
        if vol_ratio1 > vol_ratio2 * 1.5:
            scores["token1"] += 1
        elif vol_ratio2 > vol_ratio1 * 1.5:
            scores["token2"] += 1

        if scores["token1"] > scores["token2"]:
            result["winner"] = "token1"
            result["winner_symbol"] = t1["symbol"]
        elif scores["token2"] > scores["token1"]:
            result["winner"] = "token2"
            result["winner_symbol"] = t2["symbol"]
        else:
            result["winner"] = "tie"

        result["comparison"] = {
            "liq": f"{t1['symbol']}: ${t1['liquidity_usd']:,.0f} vs {t2['symbol']}: ${t2['liquidity_usd']:,.0f}",
            "mcap": f"{t1['symbol']}: ${t1['market_cap']:,.0f} vs {t2['symbol']}: ${t2['market_cap']:,.0f}",
            "volume": f"{t1['symbol']}: ${t1['volume_24h']:,.0f} vs {t2['symbol']}: ${t2['volume_24h']:,.0f}",
            "scores": scores,
        }

    return result


def detect_pump_patterns(results: list) -> list:
    patterns = []

    for r in results:
        pc = r.get("price_change_24h", 0) or 0
        mcap = r.get("market_cap", 0)
        vol = r.get("volume_24h", 0)
        age = r.get("age_minutes", 999)
        holders = r.get("score", {}).get("details", {}).get("holders", {}).get("total_holders", 0)
        pro = r.get("professional", {})

        if age < 30 and mcap < 50000 and pc > 100:
            patterns.append({"symbol": r.get("symbol", "?"), "pattern": "EARLY_PUMP", "description": "New token with explosive growth"})

        elif mcap < 10000 and isinstance(holders, (int, float)) and holders > 100:
            patterns.append({"symbol": r.get("symbol", "?"), "pattern": "LOW_MCAP_HIGH_HOLDERS", "description": "Low MCap token with strong community"})

        elif vol > mcap * 3 and mcap > 0:
            patterns.append({"symbol": r.get("symbol", "?"), "pattern": "VOLUME_SPIKE", "description": "Volume 3x MCap - high interest"})

        elif pc < -50 and mcap < 30000:
            patterns.append({"symbol": r.get("symbol", "?"), "pattern": "DIP_OPPORTUNITY", "description": "Big dip on low MCap - potential reversal"})

        if pc > 500 and age < 60:
            patterns.append({"symbol": r.get("symbol", "?"), "pattern": "MULTIPLIER", "description": f"{pc:.0f}% gain in {age:.0f}m - potential 10x"})

    return patterns
