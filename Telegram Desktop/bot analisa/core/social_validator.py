from typing import Dict
from utils.client import HttpClient


async def validate_social_links(profile_links: Dict) -> Dict:
    client = await HttpClient.get_instance()

    results = {
        "twitter_valid": None,
        "telegram_valid": None,
        "website_valid": None,
        "twitter_handle": None,
    }

    twitter_url = profile_links.get("twitter")
    if twitter_url:
        try:
            resp = await client.get(twitter_url)
            results["twitter_valid"] = True
            if "x.com/" in str(twitter_url):
                results["twitter_handle"] = str(twitter_url).split("/")[-1].split("?")[0]
        except Exception:
            results["twitter_valid"] = False

    telegram_url = profile_links.get("telegram")
    if telegram_url:
        try:
            resp = await client.get(telegram_url)
            results["telegram_valid"] = True
        except Exception:
            results["telegram_valid"] = False

    website = profile_links.get("website")
    if website:
        try:
            resp = await client.get(website)
            results["website_valid"] = True
        except Exception:
            results["website_valid"] = False

    return results
