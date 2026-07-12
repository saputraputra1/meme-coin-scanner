import re
from typing import Dict, List
from utils.client import HttpClient


async def get_social_sentiment(token_data: Dict) -> Dict:
    profile_links = token_data.get("profile_links", {})
    social_links = token_data.get("score", {}).get("details", {}).get("social", {}).get("links", [])

    twitter_url = profile_links.get("twitter") or _find_link(token_data, "twitter") or _find_link(token_data, "x.com")
    telegram_url = profile_links.get("telegram") or _find_link(token_data, "telegram") or _find_link(token_data, "t.me")
    website_url = profile_links.get("website") or _find_link(token_data, "website")

    twitter_handle = None
    if twitter_url:
        try:
            parts = str(twitter_url).split("/")
            for i, p in enumerate(parts):
                if p in ("twitter.com", "x.com") and i + 1 < len(parts):
                    twitter_handle = parts[i + 1].split("?")[0]
                    break
        except Exception:
            pass

    return {
        "has_twitter": bool(twitter_url),
        "has_telegram": bool(telegram_url),
        "has_website": bool(website_url),
        "twitter_handle": twitter_handle,
        "twitter_url": twitter_url,
        "telegram_url": telegram_url,
        "website_url": website_url,
        "social_count": sum([bool(twitter_url), bool(telegram_url), bool(website_url)]),
        "social_score": _calculate_social_score(twitter_url, telegram_url, website_url, token_data),
    }


def _find_link(data: Dict, keyword: str) -> str:
    for key, value in data.items():
        if isinstance(value, str) and keyword in value.lower():
            return value

    base_token = data.get("base_token", {})
    if isinstance(base_token, dict):
        for key, value in base_token.items():
            if isinstance(value, str) and keyword in value.lower():
                return value

    return ""


def _calculate_social_score(twitter: str, telegram: str, website: str, token_data: Dict) -> int:
    score = 0

    if twitter:
        score += 30
    if telegram:
        score += 25
    if website:
        score += 15

    name = (token_data.get("name", "") or "").lower()
    symbol = (token_data.get("symbol", "") or "").lower()

    meme_keywords = ["pepe", "doge", "wojak", "chad", "meme", "cat", "dog", "moon",
                     "inu", "shib", "bonk", "wif", "fart", "rat", "coin", "ai", "bot",
                     "sol", "pump", "gem", "alpha", "based", "community", "cto"]

    for kw in meme_keywords:
        if kw in name or kw in symbol:
            score += 5
            break

    if token_data.get("age_minutes", 999) < 30:
        score += 10

    return min(100, score)
