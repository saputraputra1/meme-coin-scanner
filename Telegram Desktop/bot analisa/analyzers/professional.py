from typing import Dict


BEARISH_KEYWORDS = ["dump", "ponzi", "scam", "rug", "dead", "jeet", "jeeted"]
BULLISH_KEYWORDS = ["gem", "alpha", "safe", "v2", "based", "community", "cto", "launch"]


def determine_signal(result: Dict) -> Dict:
    score = result.get("score", {})
    total = score.get("total_score", 0)
    details = score.get("details", {})
    safety = details.get("safety", {})
    safety_checks = safety.get("checks", {})
    liquidity = details.get("liquidity", {})
    holders = details.get("holders", {})
    social = details.get("social", {})
    deployer = result.get("deployer_check", {}).get("stats", {})
    bundler = result.get("bundler_check", {})
    age = result.get("age_minutes", 999)
    mcap = liquidity.get("market_cap", 0)
    liq = liquidity.get("liquidity_usd", 0)
    volume_24h = result.get("volume_24h", 0)
    price_change = result.get("price_change_24h", 0) or 0

    safety_score = safety.get("score", 0)
    holder_score = holders.get("score", 0)
    holder_total = holders.get("total_holders", 0)
    top10 = holders.get("top10_concentration_pct", 100)
    is_honeypot = safety_checks.get("honeypot_detected", False)
    has_lp_risk = safety_checks.get("has_lp_risk", False)
    deployer_status = deployer.get("status", "unknown")
    deployer_rug = deployer.get("rug_count", 0)
    social_links = social.get("links", [])
    is_bundled = bundler.get("is_bundled", False) if bundler else False
    can_swap = safety_checks.get("can_swap", False)
    price_impact = safety_checks.get("price_impact", 100) if isinstance(safety_checks.get("price_impact"), (int, float)) else 100
    name = (result.get("name", "") or "").lower()
    symbol = (result.get("symbol", "") or "").lower()

    sm = result.get("smart_money", {})
    sm_insider = sm.get("insider_selling", False)
    sm_holders = sm.get("smart_holder_count", 0)
    sm_risk = sm.get("risk", "unknown")
    narratives = ", ".join(result.get("narratives", []) or [])

    concerns = []
    positives = []

    if is_honeypot is True:
        concerns.append("Honeypot detected")
    if has_lp_risk:
        concerns.append("LP unlock risk")
    if is_bundled:
        concerns.append("Bundled launch")
    if deployer_status == "suspicious" or deployer_rug > 0:
        concerns.append("Deployer rug history")
    if not can_swap or price_impact >= 90:
        concerns.append("Cannot trade")
    if isinstance(top10, (int, float)) and top10 > 60:
        concerns.append("Holder concentrated")
    if holder_total == "?" or holder_total == 0:
        concerns.append("Holder data unavailable — high rug risk")
    if isinstance(mcap, (int, float)) and mcap < 3000:
        concerns.append("Micro market cap")
    if isinstance(liq, (int, float)) and liq < 3000:
        concerns.append("Very low liquidity")
    if not social_links:
        concerns.append("No social presence")
    if age < 5:
        concerns.append("Extremely new token")
    if sm_insider:
        concerns.append("Insider selling detected")
    if sm_risk == "high":
        concerns.append("High smart money risk")

    if safety_score >= 80:
        positives.append("Excellent safety")
    if deployer_status == "trusted":
        positives.append("Trusted deployer")
    if isinstance(top10, (int, float)) and top10 < 25:
        positives.append("Good distribution")
    if isinstance(holder_total, (int, float)) and holder_total >= 100:
        positives.append("Many holders")
    if isinstance(liq, (int, float)) and isinstance(mcap, (int, float)) and liq / max(mcap, 1) > 0.15:
        positives.append("Strong liquidity")
    if isinstance(volume_24h, (int, float)) and isinstance(liq, (int, float)) and liq > 0 and volume_24h / liq > 0.5:
        positives.append("Active trading")
    if isinstance(price_change, (int, float)) and price_change > 50:
        positives.append("Strong momentum")
    if social_links and len(social_links) >= 2:
        positives.append("Active social media")
    if not is_bundled and age < 30:
        positives.append("Organic launch")
    if sm_holders > 0:
        positives.append(f"Smart money backing ({sm_holders} wallet{'s' if sm_holders > 1 else ''})")
    if narratives:
        positives.append(f"Narratives: {narratives}")

    safe_buy = safety_score >= 75 and not concerns
    if safety_score >= 80 and len(concerns) == 0 and len(positives) >= 3:
        signal = "STRONG_BUY"
        signal_label = "STRONG BUY"
    elif safety_score >= 60 and len(concerns) <= 1:
        signal = "BUY"
        signal_label = "BUY"
    elif is_honeypot is True or len(concerns) >= 4:
        signal = "AVOID"
        signal_label = "AVOID"
    elif len(concerns) >= 2:
        signal = "WATCH"
        signal_label = "WATCH"
    else:
        signal = "BUY"
        signal_label = "BUY"

    if isinstance(top10, (int, float)) and top10 > 70:
        signal = "AVOID"
        signal_label = "AVOID"
        if "Extreme holder concentration" not in concerns:
            concerns.append("Extreme holder concentration (>{:.0f}%)".format(top10))
    elif isinstance(top10, (int, float)) and top10 > 50:
        if signal in ("STRONG_BUY", "BUY"):
            signal = "WATCH"
            signal_label = "WATCH"
    if holder_total == "?" or holder_total == 0:
        if signal in ("STRONG_BUY", "BUY"):
            signal = "WATCH"
            signal_label = "WATCH"

    confidence = 10
    if is_honeypot is True or not can_swap:
        confidence = 0
    else:
        confidence -= len(concerns) * 2
        confidence += len(positives)
        if deployer_status == "trusted":
            confidence += 2
        if deployer_status == "suspicious":
            confidence -= 3
        if safety_score >= 80:
            confidence += 2
        if isinstance(top10, (int, float)) and top10 < 30:
            confidence += 1
        if isinstance(top10, (int, float)) and top10 > 50:
            confidence -= 3
        if isinstance(top10, (int, float)) and top10 > 70:
            confidence -= 5
        if holder_total == "?" or holder_total == 0:
            confidence -= 4
        if sm_insider:
            confidence -= 3
        elif sm_holders > 0:
            confidence += min(sm_holders, 2)
        if sm_risk == "high":
            confidence -= 2
        elif sm_risk == "low":
            confidence += 1
        confidence = max(0, min(10, confidence))

    if confidence >= 8:
        position = "3-5% portfolio"
    elif confidence >= 5:
        position = "1-3% portfolio"
    elif confidence >= 3:
        position = "1% portfolio"
    else:
        position = "SKIP"

    return {
        "signal": signal,
        "signal_label": signal_label,
        "confidence": confidence,
        "position_recommendation": position,
        "concerns": concerns,
        "positives": positives,
        "concern_count": len(concerns),
        "positive_count": len(positives),
        "is_safe_buy": safe_buy,
        "summary": _generate_summary(signal, confidence, concerns, positives, position),
    }


def _generate_summary(signal: str, confidence: int, concerns: list, positives: list, position: str) -> str:
    if signal == "STRONG_BUY":
        return f"Excellent entry opportunity. {len(positives)} positive signals. Recommended {position}."
    elif signal == "BUY":
        return f"Favorable entry. {len(positives)} strengths, {len(concerns)} concerns. Position size: {position}."
    elif signal == "WATCH":
        c = concerns[:2] if concerns else ["multiple risk factors"]
        return f"Monitor first. Issues: {', '.join(c)}. Position: {position}."
    elif signal == "AVOID":
        c = concerns[:2] if concerns else ["high risk"]
        return f"Not recommended. {', '.join(c)}. Position: {position}."
    return "See details for full analysis."


def build_holder_bar(top10_pct, top5_pct=None, width=12) -> str:
    if isinstance(top10_pct, str):
        return "?" * width

    pct = min(100, max(0, top10_pct))
    filled = int((pct / 100) * width)
    empty = width - filled

    if pct <= 25:
        color = "green"
    elif pct <= 50:
        color = "yellow"
    else:
        color = "red"

    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"


def holder_health_label(top10_pct, total) -> str:
    if isinstance(top10_pct, str):
        return "UNKNOWN"
    if top10_pct <= 15 and isinstance(total, (int, float)) and total >= 100:
        return "EXCELLENT"
    if top10_pct <= 25:
        return "GOOD"
    if top10_pct <= 40:
        return "FAIR"
    if top10_pct <= 60:
        return "CONCERNING"
    return "POOR"
