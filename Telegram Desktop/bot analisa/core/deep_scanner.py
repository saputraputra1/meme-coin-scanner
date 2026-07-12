import asyncio
from typing import Dict, List
from core.dexscreener import fetch_trending_solana, fetch_new_pairs
from core.pumpfun import fetch_new_launches
from config import MEME_SEARCH_TERMS
from utils.client import HttpClient

JUPITER_TOKENS = "https://quote-api.jup.ag/v6/tokens"


async def deep_scan(max_age_minutes: int = 120, max_results: int = 60) -> List[Dict]:
    sources = await asyncio.gather(
        fetch_trending_solana(),
        _scan_multi_keyword(max_age_minutes),
        _fetch_pumpfun_tokens(),
        _fetch_jupiter_trending(),
        return_exceptions=True
    )

    trending, keyword_pairs, pumpfun_tokens, jupiter_tokens = sources

    if isinstance(trending, Exception):
        trending = []
    if isinstance(keyword_pairs, Exception):
        keyword_pairs = []
    if isinstance(pumpfun_tokens, Exception):
        pumpfun_tokens = []
    if isinstance(jupiter_tokens, Exception):
        jupiter_tokens = []

    all_pairs = list(trending) if isinstance(trending, list) else []

    dedup_addr = set()
    dedup_token = set()
    for p in all_pairs:
        dedup_addr.add(p.get("pair_address", ""))
        dedup_token.add(p.get("base_token", {}).get("address", ""))

    for p in (keyword_pairs if isinstance(keyword_pairs, list) else []):
        addr = p.get("pair_address", "")
        token = p.get("base_token", {}).get("address", "")
        if addr and addr not in dedup_addr and token not in dedup_token:
            dedup_addr.add(addr)
            dedup_token.add(token)
            all_pairs.append(p)

    for p in (pumpfun_tokens if isinstance(pumpfun_tokens, list) else []):
        addr = p.get("pair_address", "")
        token = p.get("base_token", {}).get("address", addr)
        if (addr or token) and addr not in dedup_addr and token not in dedup_token:
            dedup_addr.add(addr)
            dedup_token.add(token)
            mcap = p.get("market_cap", 0)
            if mcap < 2000:
                continue
            all_pairs.append(p)

    for p in (jupiter_tokens if isinstance(jupiter_tokens, list) else []):
        addr = p.get("pair_address", "")
        token = p.get("base_token", {}).get("address", addr)
        vol = p.get("volume_24h", 0)
        if (addr or token) and addr not in dedup_addr and token not in dedup_token:
            if vol < 5000:
                continue
            dedup_addr.add(addr)
            dedup_token.add(token)
            all_pairs.append(p)

    return all_pairs[:max_results]


async def _scan_multi_keyword(max_age_minutes: int) -> List[Dict]:
    jobs = []
    for term in MEME_SEARCH_TERMS:
        jobs.append(fetch_new_pairs(term, max_age_minutes=max_age_minutes))

    results = await asyncio.gather(*jobs, return_exceptions=True)
    all_pairs = []
    for r in results:
        if not isinstance(r, Exception) and isinstance(r, list):
            all_pairs.extend(r)

    return all_pairs


async def _fetch_pumpfun_tokens() -> List[Dict]:
    try:
        coins = await fetch_new_launches(limit=30)
    except Exception:
        return []

    pairs = []
    for coin in coins:
        mint = coin.get("mint", "")
        pairs.append({
            "chain": "solana",
            "dex": "pump.fun",
            "pair_address": mint,
            "base_token": {
                "address": mint,
                "name": coin.get("name", "?"),
                "symbol": coin.get("symbol", "?"),
            },
            "quote_token": {"symbol": "SOL"},
            "price_usd": 0,
            "liquidity_usd": float(coin.get("market_cap_sol", 0) or 0) * 0.6,
            "volume_24h": 0,
            "market_cap": float(coin.get("market_cap_sol", 0) or 0),
            "created_at": coin.get("created_timestamp"),
            "url": f"https://pump.fun/{mint}",
            "labels": [],
            "age_minutes": 0,
        })

    return pairs


async def _fetch_jupiter_trending() -> List[Dict]:
    client = await HttpClient.get_instance()
    try:
        tokens = await client.get(JUPITER_TOKENS)
    except Exception:
        return []

    if not isinstance(tokens, list):
        return []

    sol_tokens = [t for t in tokens if t.get("chainId") == 0] if any("chainId" in t for t in tokens) else tokens
    sorted_tokens = sorted(sol_tokens, key=lambda x: float(x.get("daily_volume", 0) or 0), reverse=True)

    pairs = []
    for token in sorted_tokens[:20]:
        addr = token.get("address", "")
        pairs.append({
            "chain": "solana",
            "dex": "jupiter",
            "pair_address": addr,
            "base_token": {
                "address": addr,
                "name": token.get("name", "?"),
                "symbol": token.get("symbol", "?"),
            },
            "quote_token": {"symbol": "SOL"},
            "price_usd": 0,
            "liquidity_usd": 0,
            "volume_24h": float(token.get("daily_volume", 0) or 0),
            "market_cap": 0,
            "url": f"https://dexscreener.com/solana/{addr}",
            "labels": [],
            "age_minutes": 0,
        })

    return pairs
