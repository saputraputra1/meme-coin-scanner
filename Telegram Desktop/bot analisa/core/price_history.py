import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from utils.client import HttpClient

DEXSCREENER_CANDLES = "https://api.dexscreener.com/latest/dex/candles"
DEXSCREENER_PRICE = "https://api.dexscreener.com/latest/dex/tokens"


async def get_price_history(token_address: str, pair_address: str = "", interval: str = "1h", limit: int = 24) -> Dict:
    client = await HttpClient.get_instance()

    try:
        data = await client.get(f"{DEXSCREENER_PRICE}/{token_address}")
    except Exception:
        return _empty_history()

    pairs = data.get("pairs", []) if data else []
    if not pairs:
        return _empty_history()

    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol_pairs:
        return _empty_history()

    pair = sol_pairs[0]
    price_usd = float(pair.get("priceUsd", 0) or 0)
    price_change = pair.get("priceChange", {})
    h1 = float(price_change.get("h1", 0) or 0)
    h6 = float(price_change.get("h6", 0) or 0)
    h24 = float(price_change.get("h24", 0) or 0)
    m5 = float(price_change.get("m5", 0) or 0)

    volume = pair.get("volume", {})
    vol_5m = float(volume.get("m5", 0) or 0)
    vol_1h = float(volume.get("h1", 0) or 0)
    vol_6h = float(volume.get("h6", 0) or 0)
    vol_24h = float(volume.get("h24", 0) or 0)

    txns = pair.get("txns", {})
    buys_5m = txns.get("m5", {}).get("buys", 0)
    sells_5m = txns.get("m5", {}).get("sells", 0)
    buys_1h = txns.get("h1", {}).get("buys", 0)
    sells_1h = txns.get("h1", {}).get("sells", 0)
    buys_6h = txns.get("h6", {}).get("buys", 0)
    sells_6h = txns.get("h6", {}).get("sells", 0)

    buy_sell_5m = buys_5m / max(sells_5m, 1)
    buy_sell_1h = buys_1h / max(sells_1h, 1)
    buy_sell_6h = buys_6h / max(sells_6h, 1)

    trend = _calculate_trend(m5, h1, h6, h24)
    volume_trend = _calculate_volume_trend(vol_5m, vol_1h, vol_6h, vol_24h)
    buy_pressure = _calculate_buy_pressure(buy_sell_5m, buy_sell_1h, buy_sell_6h)

    price_target = _estimate_target(price_usd, h1, h6, h24, buy_pressure)
    stop_loss = _estimate_stop(price_usd, h1, h6)

    return {
        "price_usd": price_usd,
        "change_5m": m5,
        "change_1h": h1,
        "change_6h": h6,
        "change_24h": h24,
        "volume_5m": vol_5m,
        "volume_1h": vol_1h,
        "volume_6h": vol_6h,
        "volume_24h": vol_24h,
        "buys_5m": buys_5m,
        "sells_5m": sells_5m,
        "buys_1h": buys_1h,
        "sells_1h": sells_1h,
        "buy_sell_ratio_5m": round(buy_sell_5m, 2),
        "buy_sell_ratio_1h": round(buy_sell_1h, 2),
        "trend": trend,
        "volume_trend": volume_trend,
        "buy_pressure": buy_pressure,
        "estimated_target_pct": price_target,
        "estimated_stop_pct": stop_loss,
        "multi_timeframe": {
            "5m": {"change": m5, "buys": buys_5m, "sells": sells_5m, "ratio": round(buy_sell_5m, 2)},
            "1h": {"change": h1, "buys": buys_1h, "sells": sells_1h, "ratio": round(buy_sell_1h, 2)},
            "6h": {"change": h6, "buys": buys_6h, "sells": sells_6h, "ratio": round(buy_sell_6h, 2)},
            "24h": {"change": h24},
        },
    }


def _calculate_trend(m5: float, h1: float, h6: float, h24: float) -> str:
    if m5 > 5 and h1 > 10:
        return "strong_uptrend"
    elif m5 > 0 and h1 > 0:
        return "uptrend"
    elif m5 < -5 and h1 < -10:
        return "strong_downtrend"
    elif m5 < 0 and h1 < 0:
        return "downtrend"
    elif h1 > 0 and h6 > 0 and h24 > 0:
        return "consistent_up"
    elif h1 < 0 and h6 < 0 and h24 < 0:
        return "consistent_down"
    else:
        return "sideways"


def _calculate_volume_trend(vol_5m: float, vol_1h: float, vol_6h: float, vol_24h: float) -> str:
    if vol_24h == 0:
        return "no_volume"

    vol_per_hour = vol_24h / 24
    vol_6h_per_hour = vol_6h / 6

    if vol_1h > vol_per_hour * 3:
        return "surging"
    elif vol_1h > vol_per_hour * 1.5:
        return "rising"
    elif vol_1h < vol_per_hour * 0.3:
        return "declining"
    else:
        return "stable"


def _calculate_buy_pressure(ratio_5m: float, ratio_1h: float, ratio_6h: float) -> str:
    avg = (ratio_5m + ratio_1h + ratio_6h) / 3

    if ratio_5m > 2.0 and ratio_1h > 1.5:
        return "very_strong"
    elif ratio_5m > 1.5 and ratio_1h > 1.2:
        return "strong"
    elif ratio_5m > 1.0 and ratio_1h > 1.0:
        return "moderate"
    elif ratio_5m < 0.5 and ratio_1h < 0.7:
        return "weak"
    elif ratio_5m < 0.3 and ratio_1h < 0.5:
        return "very_weak"
    else:
        return "neutral"


def _estimate_target(price: float, h1: float, h6: float, h24: float, buy_pressure: str) -> float:
    if price <= 0:
        return 0

    base_target = 0
    if h1 > 0:
        base_target += h1 * 0.5
    if h6 > 0:
        base_target += h6 * 0.3
    if h24 > 0:
        base_target += h24 * 0.2

    multipliers = {
        "very_strong": 2.0,
        "strong": 1.5,
        "moderate": 1.0,
        "neutral": 0.5,
        "weak": 0.2,
        "very_weak": 0,
    }
    base_target *= multipliers.get(buy_pressure, 0.5)

    return round(min(max(base_target, 10), 500), 0)


def _estimate_stop(price: float, h1: float, h6: float) -> float:
    if price <= 0:
        return -30

    volatility = abs(h1) + abs(h6)
    if volatility > 100:
        return -30
    elif volatility > 50:
        return -25
    elif volatility > 20:
        return -20
    else:
        return -15


def _empty_history() -> Dict:
    return {
        "price_usd": 0,
        "change_5m": 0,
        "change_1h": 0,
        "change_6h": 0,
        "change_24h": 0,
        "volume_5m": 0,
        "volume_1h": 0,
        "volume_6h": 0,
        "volume_24h": 0,
        "buys_5m": 0,
        "sells_5m": 0,
        "buys_1h": 0,
        "sells_1h": 0,
        "buy_sell_ratio_5m": 0,
        "buy_sell_ratio_1h": 0,
        "trend": "unknown",
        "volume_trend": "unknown",
        "buy_pressure": "unknown",
        "estimated_target_pct": 0,
        "estimated_stop_pct": -30,
        "multi_timeframe": {},
    }
