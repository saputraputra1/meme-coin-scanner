from typing import Dict, List, Optional
from utils.client import HttpClient

SOLSCAN_BASE = "https://public-api.solscan.io"


async def get_token_holders(token_address: str, limit: int = 20) -> List[Dict]:
    client = await HttpClient.get_instance()
    try:
        data = await client.get(
            f"{SOLSCAN_BASE}/token/holders",
            params={"tokenAddress": token_address, "limit": limit, "offset": 0},
        )
    except Exception:
        return []

    return data.get("data", []) if isinstance(data, dict) else []


async def get_token_meta(token_address: str) -> Optional[Dict]:
    client = await HttpClient.get_instance()
    try:
        data = await client.get(f"{SOLSCAN_BASE}/token/meta", params={"tokenAddress": token_address})
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def analyze_holders(token_address: str) -> Dict:
    holders = await get_token_holders(token_address, limit=20)
    total_holders = len(holders)

    if total_holders == 0:
        return {
            "total_holders": 0,
            "top10_pct": 100,
            "top10_count": 0,
            "is_concentrated": True,
            "risk": "high",
        }

    total_supply = sum(float(h.get("amount", 0)) for h in holders)
    if total_supply == 0:
        total_supply = 1

    top10_amount = sum(float(h.get("amount", 0)) for h in holders[:10])
    top10_pct = (top10_amount / total_supply) * 100

    risk = "low" if top10_pct < 30 else "medium" if top10_pct < 60 else "high"

    return {
        "total_holders": total_holders,
        "top10_pct": round(top10_pct, 2),
        "top10_count": min(10, total_holders),
        "is_concentrated": top10_pct > 50,
        "risk": risk,
    }
