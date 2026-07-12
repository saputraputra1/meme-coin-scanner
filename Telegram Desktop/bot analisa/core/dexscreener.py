import asyncio
from datetime import datetime, timezone
from typing import List, Dict
from utils.client import HttpClient

DEXSCREENER_BASE = "https://api.dexscreener.com"


async def fetch_new_pairs(query: str = "meme", max_age_minutes: int = 60) -> List[Dict]:
    client = await HttpClient.get_instance()

    try:
        data = await client.get(f"{DEXSCREENER_BASE}/latest/dex/search", params={"q": query})
    except Exception:
        return []

    pairs = data.get("pairs", []) if data else []
    now = datetime.now(timezone.utc)
    recent = []

    for pair in pairs:
        if pair.get("chainId") != "solana":
            continue

        created_at = pair.get("pairCreatedAt")
        if created_at:
            age = (now - datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)).total_seconds() / 60
            if age > max_age_minutes:
                continue

        liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
        mcap = float(pair.get("fdv", 0) or 0)

        recent.append({
            "chain": "solana",
            "dex": pair.get("dexId"),
            "pair_address": pair.get("pairAddress"),
            "base_token": pair.get("baseToken", {}),
            "quote_token": pair.get("quoteToken", {}),
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "price_native": pair.get("priceNative"),
            "liquidity_usd": liquidity,
            "volume_24h": volume_24h,
            "market_cap": mcap,
            "created_at": pair.get("pairCreatedAt"),
            "url": pair.get("url"),
            "labels": pair.get("labels", []),
        })

    return recent


async def fetch_trending_solana() -> List[Dict]:
    client = await HttpClient.get_instance()

    try:
        profiles = await client.get(f"{DEXSCREENER_BASE}/token-profiles/latest/v1")
    except Exception:
        return []

    solana_addresses = [p["tokenAddress"] for p in profiles if p.get("chainId") == "solana"]

    results = []
    for addr in solana_addresses[:20]:
        info = await _fetch_pair_by_token(addr)
        if info:
            info["profile_links"] = _extract_social_links(profiles, addr)
            results.append(info)
        await asyncio.sleep(0.2)

    results.sort(key=lambda x: x.get("volume_24h", 0), reverse=True)
    return results


async def _fetch_pair_by_token(token_address: str) -> Dict | None:
    client = await HttpClient.get_instance()
    try:
        data = await client.get(f"{DEXSCREENER_BASE}/latest/dex/tokens/{token_address}")
    except Exception:
        return None

    pairs = data.get("pairs", []) if data else []
    if not pairs:
        return None

    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol_pairs:
        return None

    pair = max(sol_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))

    liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
    mcap = float(pair.get("fdv", 0) or 0)
    volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
    created_at = pair.get("pairCreatedAt")

    now = datetime.now(timezone.utc)
    age_minutes = 0
    if created_at:
        age_minutes = (now - datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)).total_seconds() / 60

    h24 = pair.get("txns", {}).get("h24", {})
    txns_24h = h24.get("buys", 0) + h24.get("sells", 0) if isinstance(h24, dict) else 0

    return {
        "chain": "solana",
        "dex": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
        "base_token": pair.get("baseToken", {}),
        "quote_token": pair.get("quoteToken", {}),
        "price_usd": float(pair.get("priceUsd", 0) or 0),
        "liquidity_usd": liquidity,
        "volume_24h": volume_24h,
        "market_cap": mcap,
        "txns_24h": txns_24h,
        "age_minutes": age_minutes,
        "created_at": created_at,
        "url": pair.get("url"),
        "labels": pair.get("labels", []),
        "price_change": pair.get("price_change", pair.get("priceChange", {})),
    }


def _extract_social_links(profiles: list, token_address: str) -> Dict:
    for p in profiles:
        if p.get("tokenAddress") == token_address:
            links = {"twitter": None, "telegram": None, "website": None}
            for link in (p.get("links") or []):
                url = link.get("url", "")
                link_type = link.get("type", "")
                label = link.get("label", "")
                if link_type == "twitter" or "twitter" in url or "x.com" in url:
                    links["twitter"] = url
                elif link_type == "telegram" or "telegram" in url or "t.me" in url:
                    links["telegram"] = url
                elif "website" in str(link_type or label).lower() or url not in [links["twitter"], links["telegram"]]:
                    links["website"] = links["website"] or url
            return links
    return {"twitter": None, "telegram": None, "website": None}


async def get_token_info(token_address: str) -> Dict | None:
    return await _fetch_pair_by_token(token_address)
