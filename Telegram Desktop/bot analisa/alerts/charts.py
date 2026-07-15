import asyncio
import json
import urllib.parse
from typing import Dict, List
import httpx


async def _shorten_chart_url(chart_config: dict, width: int, height: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://quickchart.io/v1/chart/create",
                json={"chart": chart_config, "width": width, "height": height},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("url", "")
    except Exception:
        pass
    return ""


async def generate_score_chart_url(result: Dict, width: int = 400, height: int = 200) -> str:
    score = result.get("score", {})
    breakdown = score.get("breakdown", {})

    safety = breakdown.get("safety", 0)
    liquidity = breakdown.get("liquidity", 0)
    holders = breakdown.get("holders", 0)
    social = breakdown.get("social", 0)
    deployer_bonus = result.get("score", {}).get("deployer_bonus", "")
    deployer_penalty = result.get("score", {}).get("deployer_penalty", "")
    deployer_val = 5 if deployer_bonus else (-15 if deployer_penalty else 0)

    labels = ["Safety", "Liquid", "Holder", "Social"]
    values = [safety, liquidity, holders, social]
    max_vals = [40, 25, 20, 15]

    if deployer_val != 0:
        labels.append("Deployer")
        values.append(max(0, deployer_val) if deployer_val > 0 else deployer_val)
        max_vals.append(15)

    colors = [
        "rgba(34,197,94,0.8)" if safety >= 30 else "rgba(234,179,8,0.8)" if safety >= 20 else "rgba(239,68,68,0.8)",
        "rgba(34,197,94,0.8)" if liquidity >= 18 else "rgba(234,179,8,0.8)" if liquidity >= 10 else "rgba(239,68,68,0.8)",
        "rgba(34,197,94,0.8)" if holders >= 15 else "rgba(234,179,8,0.8)" if holders >= 8 else "rgba(239,68,68,0.8)",
        "rgba(34,197,94,0.8)" if social >= 10 else "rgba(234,179,8,0.8)" if social >= 5 else "rgba(239,68,68,0.8)",
    ]
    if deployer_val != 0:
        colors.append("rgba(34,197,94,0.8)" if deployer_val > 0 else "rgba(239,68,68,0.8)")

    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": values,
                "backgroundColor": colors,
                "borderRadius": 4,
            }]
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"{result.get('symbol', '?')} Score: {score.get('total_score', 0)}/100",
                    "font": {"size": 14, "weight": "bold"},
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "max": max(max_vals) * 1.1,
                    "beginAtZero": True,
                    "ticks": {"font": {"size": 10}},
                    "grid": {"color": "rgba(200,200,200,0.2)"},
                },
                "x": {
                    "ticks": {"font": {"size": 10}},
                }
            },
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"{result.get('symbol', '?')} Score: {score.get('total_score', 0)}/100",
                    "font": {"size": 14, "weight": "bold"}
                },
                "legend": {"display": False}
            }
        }
    }

    short = await _shorten_chart_url(chart_config, width, height)
    if short:
        return short
    config_str = json.dumps(chart_config)
    encoded = urllib.parse.quote(config_str)
    return f"https://quickchart.io/chart?w={width}&h={height}&c={encoded}"


async def generate_price_chart_url(symbol: str, current_price: float, change_24h: float, prices: List[float] = None, width: int = 500, height: int = 180) -> str:
    if prices and len(prices) > 1:
        data = prices
    else:
        import random
        steps = 12
        if current_price and change_24h:
            start_price = current_price / (1 + change_24h / 100)
            step_change = (current_price - start_price) / steps
            data = []
            for i in range(steps + 1):
                noise = random.uniform(-0.3, 0.3) * abs(step_change) if abs(step_change) > 0 else 0
                data.append(round(start_price + step_change * i + noise, 10))
        else:
            data = [0.0001] * 6

    border_color = "rgba(34,197,94,1)" if change_24h >= 0 else "rgba(239,68,68,1)"
    bg_color = "rgba(34,197,94,0.15)" if change_24h >= 0 else "rgba(239,68,68,0.15)"

    chart_config = {
        "type": "line",
        "data": {
            "labels": [""] * len(data),
            "datasets": [{
                "data": data,
                "borderColor": border_color,
                "borderWidth": 2,
                "backgroundColor": bg_color,
                "fill": True,
                "pointRadius": 0,
                "tension": 0.4,
            }]
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"{symbol} | 24h: {change_24h:+.0f}%",
                    "font": {"size": 12, "weight": "bold"},
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "beginAtZero": False,
                    "ticks": {"font": {"size": 9}, "callback": "function(v){return v < 0.001 ? v.toExponential(2) : v.toFixed(6)}"},
                    "grid": {"color": "rgba(200,200,200,0.2)"},
                },
                "x": {"display": False},
            }
        }
    }

    short = await _shorten_chart_url(chart_config, width, height)
    if short:
        return short
    config_str = json.dumps(chart_config)
    encoded = urllib.parse.quote(config_str)
    return f"https://quickchart.io/chart?w={width}&h={height}&c={encoded}"


async def generate_holder_chart_url(top10_pct, top5_pct=None, width=350, height=150):
    labels = ["Top5", "Top10"] if top5_pct else ["Top10"]
    values = [top5_pct, top10_pct] if top5_pct else [top10_pct]
    max_val = max(top10_pct if isinstance(top10_pct, (int, float)) else 100, 100)

    colors = [
        "rgba(239,68,68,0.7)" if (top5_pct or top10_pct) > 25 else "rgba(234,179,8,0.7)" if (top5_pct or top10_pct) > 15 else "rgba(34,197,94,0.7)",
        "rgba(239,68,68,0.7)" if (top10_pct if isinstance(top10_pct, (int, float)) else 100) > 25 else "rgba(234,179,8,0.7)",
    ][:len(labels)]

    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": values,
                "backgroundColor": colors,
                "borderRadius": 3,
            }]
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": "Holder Concentration", "font": {"size": 12}},
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "max": max_val * 1.1,
                    "ticks": {"callback": "function(v){return v+'%'}"},
                    "grid": {"color": "rgba(200,200,200,0.2)"},
                }
            }
        }
    }

    short = await _shorten_chart_url(chart_config, width, height)
    if short:
        return short
    config_str = json.dumps(chart_config)
    encoded = urllib.parse.quote(config_str)
    return f"https://quickchart.io/chart?w={width}&h={height}&c={encoded}"


async def generate_charts_for_token(result: Dict) -> Dict:
    price = result.get("price_usd", 0)
    change_24h = result.get("price_change_24h", 0) or 0
    holders = result.get("score", {}).get("details", {}).get("holders", {})

    score_chart, price_chart, holder_chart = await asyncio.gather(
        generate_score_chart_url(result),
        generate_price_chart_url(result.get("symbol", "?"), price, change_24h),
        generate_holder_chart_url(
            holders.get("top10_concentration_pct", 0) if isinstance(holders.get("top10_concentration_pct"), (int, float)) else 50,
            top5_pct=None,
        ),
    )
    return {
        "score_chart": score_chart,
        "price_chart": price_chart,
        "holder_chart": holder_chart,
    }
