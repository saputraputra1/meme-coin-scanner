from typing import List, Dict
from utils.client import HttpClient

PUMPFUN_API = "https://frontend-api-v3.pump.fun"


async def fetch_new_launches(limit: int = 30) -> List[Dict]:
    client = await HttpClient.get_instance()
    try:
        data = await client.get(
            f"{PUMPFUN_API}/coins",
            params={"offset": 0, "limit": limit, "sort": "created_timestamp", "order": "DESC"},
        )
    except Exception:
        return []

    coins = data if isinstance(data, list) else data.get("coins", [])
    results = []

    for coin in coins:
        results.append({
            "mint": coin.get("mint") or coin.get("token"),
            "name": coin.get("name", "Unknown"),
            "symbol": coin.get("symbol", "???"),
            "description": coin.get("description", ""),
            "image_url": coin.get("image_uri", ""),
            "twitter": coin.get("twitter", ""),
            "telegram": coin.get("telegram", ""),
            "website": coin.get("website", ""),
            "creator": coin.get("creator", ""),
            "market_cap_sol": float(coin.get("usd_market_cap", 0) or 0),
            "created_at": coin.get("created_timestamp"),
        })

    return results
