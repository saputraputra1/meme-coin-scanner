from typing import Dict


def analyze_liquidity(pair_data: Dict) -> Dict:
    liquidity = pair_data.get("liquidity_usd", 0)
    mcap = pair_data.get("market_cap", 0)
    volume = pair_data.get("volume_24h", 0)

    score = 0
    checks = {}

    if liquidity >= 10000:
        checks["liq_depth"] = "good"
        score += 35
    elif liquidity >= 5000:
        checks["liq_depth"] = "moderate"
        score += 20
    elif liquidity > 0:
        checks["liq_depth"] = "low"
        score += 10
    else:
        checks["liq_depth"] = "none"
        score += 0

    if mcap > 0 and liquidity > 0:
        ratio = (liquidity / mcap) * 100
        checks["liq_mcap_ratio"] = round(ratio, 2)
        if ratio >= 20:
            score += 30
        elif ratio >= 10:
            score += 20
        elif ratio >= 5:
            score += 10
    else:
        checks["liq_mcap_ratio"] = 0

    if volume > 0 and liquidity > 0:
        vol_liq_ratio = volume / liquidity
        checks["vol_liq_ratio"] = round(vol_liq_ratio, 2)
        if vol_liq_ratio >= 1.0:
            score += 20
        elif vol_liq_ratio >= 0.3:
            score += 10
    else:
        checks["vol_liq_ratio"] = 0

    if mcap < 300000:
        checks["small_mcap"] = True
        score += 15
    else:
        checks["small_mcap"] = False

    risk = "low" if score >= 70 else "medium" if score >= 40 else "high"

    return {
        "score": score,
        "checks": checks,
        "risk": risk,
        "liquidity_usd": liquidity,
        "market_cap": mcap,
        "volume_24h": volume,
    }
