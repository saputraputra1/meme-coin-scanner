from typing import Dict, List
from config import (
    SCORE_SAFETY_WEIGHT,
    SCORE_LIQUIDITY_WEIGHT,
    SCORE_HOLDER_WEIGHT,
    SCORE_SOCIAL_WEIGHT,
)


async def calculate_social_score(pair_data: Dict) -> Dict:
    base_token = pair_data.get("base_token", {})
    symbol = base_token.get("symbol", "")
    name = base_token.get("name", "")

    social_links = []
    social_urls = {}
    twitter_handle = None

    profile_links = pair_data.get("profile_links", {})
    if profile_links:
        if profile_links.get("twitter"):
            social_links.append("twitter")
            social_urls["twitter"] = profile_links.get("twitter")
            tw = profile_links.get("twitter", "")
            try:
                twitter_handle = str(tw).split("/")[-1].split("?")[0].split("status")[0].strip("/")
            except Exception:
                pass
        if profile_links.get("telegram"):
            social_links.append("telegram")
            social_urls["telegram"] = profile_links.get("telegram")
        if profile_links.get("website"):
            social_links.append("website")
            social_urls["website"] = profile_links.get("website")

    if not social_links:
        twitter_url = find_social_link(pair_data, "twitter") or find_social_link(pair_data, "x.com")
        if twitter_url:
            social_links.append("twitter")
            social_urls["twitter"] = twitter_url
            try:
                twitter_handle = str(twitter_url).split("/")[-1].split("?")[0].split("status")[0].strip("/")
            except Exception:
                pass

        telegram_url = find_social_link(pair_data, "telegram") or find_social_link(pair_data, "t.me")
        if telegram_url:
            social_links.append("telegram")
            social_urls["telegram"] = telegram_url

        website = find_social_link(pair_data, "website") or base_token.get("website", "")
        if website and "http" in str(website):
            social_links.append("website")
            social_urls["website"] = website

    # Fix #3: presence of a link used to be worth full points on its own,
    # which any scammer can fake in 30 seconds (empty TG group, dead website).
    # Now a link only earns full points once it's confirmed to actually
    # resolve; unverified links earn a much smaller amount so social score
    # can't be trivially manufactured.
    validated = {"twitter_valid": None, "telegram_valid": None, "website_valid": None}
    if social_urls:
        try:
            from core.social_validator import validate_social_links
            validated = await validate_social_links(social_urls)
        except Exception:
            pass

    score = 0
    verified_count = 0
    for link_type in social_links:
        is_valid = validated.get(f"{link_type}_valid")
        if is_valid is True:
            score += 30
            verified_count += 1
        elif is_valid is False:
            score += 5  # link exists but doesn't actually resolve — near-worthless
        else:
            score += 12  # validation unavailable/inconclusive — partial credit only

    score = min(score, 100)

    has_meme_keywords = any(
        kw in (name + symbol).lower() for kw in ["pepe", "doge", "wojak", "chad", "meme", "cat", "dog", "moon", "inu", "shib", "bonk", "wif", "fart", "rat", "coin", "ai", "bot"]
    )
    if has_meme_keywords:
        score += 5  # halved: this is a naming pattern, not a real trust signal

    has_degen_name = len(symbol) >= 6 and symbol.isupper()
    if has_degen_name:
        score += 5

    score = min(score, 100)

    return {
        "score": score,
        "has_socials": len(social_links) > 0,
        "links": social_links,
        "verified_links": verified_count,
        "twitter_handle": twitter_handle,
        "is_meme_keyword": has_meme_keywords,
        "is_degen": has_degen_name,
    }


def find_social_link(data: Dict, keyword: str) -> str | None:
    for key, value in data.items():
        if isinstance(value, str) and keyword in value.lower():
            return value

    base_token = data.get("base_token", {})
    if isinstance(base_token, dict):
        for key, value in base_token.items():
            if isinstance(value, str) and keyword in value.lower():
                return value

    return None


async def calculate_final_score(
    safety_result: Dict,
    liquidity_result: Dict,
    holder_result: Dict,
    social_result: Dict,
    pair_data: Dict,
) -> Dict:
    # Fix #6: use weights tuned from real trade outcomes when available
    # (analyzers/weight_tuner.py), falling back to the config.py defaults
    # until there's enough closed real-trade data to tune from.
    try:
        from analyzers.weight_tuner import get_current_weights
        weights = get_current_weights()
    except Exception:
        weights = {
            "safety": SCORE_SAFETY_WEIGHT,
            "liquidity": SCORE_LIQUIDITY_WEIGHT,
            "holders": SCORE_HOLDER_WEIGHT,
            "social": SCORE_SOCIAL_WEIGHT,
        }

    safety_w = safety_result["score"] * (weights["safety"] / 100)
    liq_w = liquidity_result["score"] * (weights["liquidity"] / 100)
    holder_w = holder_result["score"] * (weights["holders"] / 100)
    social_w = social_result["score"] * (weights["social"] / 100)

    final = round(safety_w + liq_w + holder_w + social_w)

    holder_data = holder_result.get("data_available", True)
    top10 = holder_result.get("top10_concentration_pct", 0)
    if not holder_data:
        final = min(final, 60)
    if isinstance(top10, (int, float)) and top10 > 70:
        final = min(final, 50)
    elif isinstance(top10, (int, float)) and top10 > 50:
        final = min(final, 70)

    verdict = "CAUTION" if final < 40 else "WATCH" if final < 70 else "POTENTIAL" if final < 85 else "HOT"

    return {
        "total_score": final,
        "verdict": verdict,
        "breakdown": {
            "safety": round(safety_w, 1),
            "liquidity": round(liq_w, 1),
            "holders": round(holder_w, 1),
            "social": round(social_w, 1),
        },
        "details": {
            "safety": safety_result,
            "liquidity": liquidity_result,
            "holders": holder_result,
            "social": social_result,
        },
    }
