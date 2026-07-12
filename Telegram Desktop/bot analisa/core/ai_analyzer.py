import json
import re
from typing import Dict, Optional
from openai import AsyncOpenAI
from config import MIMO_API_KEY

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-pro"

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL, timeout=30.0)
    return _client


def _build_structured_prompt(token_data: Dict) -> str:
    score = token_data.get("score", {})
    details = score.get("details", {})
    safety = details.get("safety", {})
    checks = safety.get("checks", {})
    liquidity = details.get("liquidity", {})
    holders = details.get("holders", {})
    deployer = token_data.get("deployer_check", {}).get("stats", {})
    pro = token_data.get("professional", {})
    auto_whales = token_data.get("auto_whales", {})
    onchain = token_data.get("onchain_metrics", {})
    social = token_data.get("social_sentiment", {})
    price_hist = token_data.get("price_history", {})
    market = token_data.get("market_context", {})

    mint_status = "Renounced" if checks.get("mint_authority") is True else "Active" if checks.get("mint_authority") is False else "Unknown"
    freeze_status = "Disabled" if checks.get("freeze_authority") is True else "Enabled" if checks.get("freeze_authority") is False else "Unknown"
    hp_status = "YES" if checks.get("honeypot_detected") is True else "No" if checks.get("honeypot_detected") is False else "Unknown"
    swap_status = "Yes" if checks.get("can_swap") is True else "No" if checks.get("can_swap") is False else "Unknown"

    holder_health = holders.get("health", "Unknown")
    holder_total = holders.get("total_holders", 0)
    if isinstance(holder_total, str):
        holder_total = 0
    top10 = holders.get("top10_concentration_pct", 0)
    if isinstance(top10, str):
        top10 = 0

    dep_status = deployer.get("status", "Unknown")
    dep_success = deployer.get("success_rate", 0)
    dep_rug = deployer.get("rug_count", 0)

    whale_pct = auto_whales.get("total_whale_supply_pct", 0)
    whale_count = auto_whales.get("whale_count", 0)

    tx_1h = onchain.get("tx_count_1h", 0)
    tx_6h = onchain.get("tx_count_6h", 0)
    buyers_1h = onchain.get("unique_buyers_1h", 0)
    sellers_1h = onchain.get("unique_sellers_1h", 0)
    ratio = onchain.get("buyer_seller_ratio", 0)
    momentum = onchain.get("momentum", "unknown")

    has_twitter = social.get("has_twitter", False)
    has_telegram = social.get("has_telegram", False)
    has_website = social.get("has_website", False)
    social_count = social.get("social_count", 0)
    twitter_handle = social.get("twitter_handle", "")

    positives = pro.get("positives", [])
    concerns = pro.get("concerns", [])

    trend = price_hist.get("trend", "unknown")
    buy_pressure = price_hist.get("buy_pressure", "unknown")
    vol_trend = price_hist.get("volume_trend", "unknown")
    mtf = price_hist.get("multi_timeframe", {})

    market_mood = market.get("market_mood", "unknown")
    sol_change = market.get("sol_change_24h", 0)
    meme_friendly = market.get("meme_friendly", False)

    sm = token_data.get("smart_money", {})
    sm_holders = sm.get("smart_holder_count", 0)
    sm_risk = sm.get("risk", "unknown")
    sm_insider = sm.get("insider_selling", False)
    sm_retention = sm.get("early_buyer_retention_pct")
    narratives = ", ".join(token_data.get("narratives", []) or ["-"])

    prompt = f"""=== ADVANCED TOKEN ANALYSIS ===

TOKEN: ${token_data.get('symbol', '?')} ({token_data.get('name', '?')})

--- SAFETY ---
Mint: {mint_status} | Freeze: {freeze_status}
Honeypot: {hp_status} | Can Swap: {swap_status}
Price Impact: {checks.get('price_impact', '?')}% | RugCheck Risks: {checks.get('risk_count', '?')}
Safety Score: {safety.get('score', 0)}/100

--- MARKET ---
MCap: ${liquidity.get('market_cap', 0):,.0f} | Liq: ${liquidity.get('liquidity_usd', 0):,.0f}
Volume 24h: ${token_data.get('volume_24h', 0):,.0f}
Price Change: 5m {price_hist.get('change_5m', 0):+.1f}% | 1h {price_hist.get('change_1h', 0):+.1f}% | 6h {price_hist.get('change_6h', 0):+.1f}% | 24h {price_hist.get('change_24h', 0):+.1f}%
Age: {token_data.get('age_minutes', 0):.0f} minutes | Dex: {token_data.get('dex', '?')}

--- PRICE ACTION ---
Trend: {trend}
Buy Pressure: {buy_pressure}
Volume Trend: {vol_trend}
Buy/Sell 5m: {mtf.get('5m', {}).get('ratio', '?')} | 1h: {mtf.get('1h', {}).get('ratio', '?')} | 6h: {mtf.get('6h', {}).get('ratio', '?')}
AI Target: +{price_hist.get('estimated_target_pct', 0):.0f}% | AI Stop: {price_hist.get('estimated_stop_pct', -30):.0f}%

--- HOLDERS ---
Total: {holder_total} | Top10: {top10:.0f}% | Health: {holder_health}
Whale Supply: {whale_pct:.1f}% ({whale_count} wallets)

--- DEPLOYER ---
Status: {dep_status} | Success: {dep_success:.0f}% | Rugs: {dep_rug}

--- ON-CHAIN ---
Tx 1h: {tx_1h} | Buyers: {buyers_1h} | Sellers: {sellers_1h} | Ratio: {ratio}x
Momentum: {momentum}

--- SOCIAL ---
Twitter: {'@' + twitter_handle if has_twitter else 'None'} | Telegram: {'Yes' if has_telegram else 'No'} | Web: {'Yes' if has_website else 'No'}

--- MARKET CONTEXT ---
SOL: {market_mood} ({sol_change:+.1f}%) | Meme-friendly: {'Yes' if meme_friendly else 'No'}

--- SMART MONEY ---
Known smart holders: {sm_holders} | Risk: {sm_risk} | Insider selling: {'YES' if sm_insider else 'No'}
Early-buyer retention: {sm_retention if sm_retention is not None else 'N/A'}%

--- NARRATIVES / SECTOR ---
Themes: {narratives}

--- ENGINE ---
Signal: {pro.get('signal', '?')} | Confidence: {pro.get('confidence', '?')}/10
Positives: {', '.join(positives[:4]) or 'None'}
Concerns: {', '.join(concerns[:4]) or 'None'}

=== ANALYZE STEP BY STEP ===
1. SAFETY: Honeypot? RugCheck clean? Mint/freeze OK?
2. LIQUIDITY: Can you sell? Liq/MCap healthy? Price impact OK?
3. HOLDERS: Distributed? Whales buying or selling?
4. MOMENTUM: 5m/1h trend + buy pressure + volume surging?
5. MARKET: SOL bullish = meme friendly?
6. DEPLOYER: Trusted? Track record?

=== OUTPUT FORMAT ===
Respond with ONLY a single JSON object, no markdown fences, no extra text before or after it. Use exactly these keys:
{{
  "signal": "STRONG_BUY" | "BUY" | "WATCH" | "AVOID",
  "confidence": <integer 1-10>,
  "reasoning": "<2-3 sentences in Indonesian>",
  "target_price_pct": "<e.g. +80%>",
  "stop_loss_pct": "<e.g. -40%>",
  "risk_level": "low" | "medium" | "high",
  "position_size": "<e.g. 1-3% portfolio, or SKIP>"
}}"""

    return prompt


async def analyze_with_ai(token_data: Dict) -> Dict:
    if not MIMO_API_KEY:
        return _fallback_response(token_data, "no_api_key")

    client = _get_client()

    try:
        response = await client.chat.completions.create(
            model=MIMO_MODEL,
            messages=[{"role": "user", "content": _build_structured_prompt(token_data)}],
            extra_body={"max_completion_tokens": 2000},
            max_tokens=2000,
            temperature=0.3,
        )

        content = ""
        reasoning_text = ""
        if response.choices:
            msg = response.choices[0].message
            content = (msg.content or "").strip()
            reasoning_text = (getattr(msg, "reasoning_content", None) or "").strip()

        if not content and reasoning_text:
            lines = reasoning_text.split("\n")
            useful = [l.strip() for l in lines if l.strip() and len(l.strip()) > 3]
            if useful:
                content = "\n".join(useful[-8:])

        if not content and reasoning_text:
            content = reasoning_text[:500]

        if not content:
            return _fallback_response(token_data, "empty_response")

        parsed = _parse_json_response(content)
        if parsed is None:
            # Model didn't return clean JSON (e.g. wrapped in prose/markdown) —
            # fall back to the old line-by-line text parser rather than
            # silently misreading the signal.
            parsed = _parse_text_response(content, token_data)

        parsed = _calibrate_confidence(parsed, token_data)
        return parsed

    except Exception as e:
        return _fallback_response(token_data, str(e)[:100])


_VALID_SIGNALS = {"STRONG_BUY", "BUY", "WATCH", "AVOID"}
_VALID_RISK = {"low", "medium", "high"}


def _parse_json_response(text: str) -> Optional[Dict]:
    """Fix #4: parse the AI's structured JSON output instead of regex-matching
    free-form text (which silently misreads signals if the model's phrasing
    or formatting drifts even slightly)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    # Model may still wrap the JSON in a sentence; extract the outermost object.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    cleaned = cleaned[start:end + 1]

    try:
        data = json.loads(cleaned)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    signal = str(data.get("signal", "")).strip().upper()
    if signal not in _VALID_SIGNALS:
        return None  # untrusted/garbage signal — force fallback to text parser

    try:
        confidence = int(data.get("confidence", 5))
    except Exception:
        confidence = 5
    confidence = max(1, min(10, confidence))

    risk_level = str(data.get("risk_level", "medium")).strip().lower()
    if risk_level not in _VALID_RISK:
        risk_level = "medium"

    reasoning = str(data.get("reasoning", "") or "")[:300]

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": reasoning,
        "target_price_pct": str(data.get("target_price_pct", "N/A")),
        "stop_loss_pct": str(data.get("stop_loss_pct", "N/A")),
        "risk_level": risk_level,
        "position_size": str(data.get("position_size", "1-3% portfolio")),
        "source": "ai",
    }


def _parse_text_response(text: str, token_data: Dict) -> Dict:
    signal = "WATCH"
    confidence = 5
    reasoning = ""
    target = "N/A"
    stop_loss = "N/A"
    risk_level = "medium"
    position = "1-3% portfolio"

    cleaned = text.replace("**", "").replace("##", "").replace("#", "").strip()

    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()

        if "sinyal" in lower and ":" in line:
            sig = line.split(":", 1)[1].strip().upper()
            for s in ["STRONG_BUY", "BUY", "WATCH", "AVOID"]:
                if s in sig:
                    signal = s
                    break

        elif "kepercayaan" in lower and ":" in line:
            nums = re.findall(r'(\d+)', line.split(":", 1)[1])
            if nums:
                confidence = max(1, min(10, int(nums[0])))

        elif "alasan" in lower and ":" in line:
            r_val = line.split(":", 1)[1].strip()
            if r_val and r_val not in ("*", "**", "-", ""):
                reasoning = r_val

        elif "target" in lower and ":" in line:
            t_val = line.split(":", 1)[1].strip()
            if t_val and t_val not in ("*", "**", "-", ""):
                target = t_val

        elif "stop" in lower and ":" in line:
            s_val = line.split(":", 1)[1].strip()
            if s_val and s_val not in ("*", "**", "-", ""):
                stop_loss = s_val

        elif "risiko" in lower and ":" in line:
            rl = line.split(":", 1)[1].strip().lower()
            if "low" in rl:
                risk_level = "low"
            elif "high" in rl:
                risk_level = "high"
            elif "medium" in rl:
                risk_level = "medium"

        elif "posisi" in lower and ":" in line:
            p_val = line.split(":", 1)[1].strip()
            if p_val and p_val not in ("*", "**", "-", ""):
                position = p_val

    if not reasoning:
        pro = token_data.get("professional", {})
        reasoning = f"Score: {token_data.get('score', {}).get('total_score', 0)}/100. {len(pro.get('positives', []))} strengths, {len(pro.get('concerns', []))} concerns."

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": reasoning[:300],
        "target_price_pct": target,
        "stop_loss_pct": stop_loss,
        "risk_level": risk_level,
        "position_size": position,
        "source": "ai",
    }


def _calibrate_confidence(parsed: Dict, token_data: Dict) -> Dict:
    confidence = parsed.get("confidence", 5)

    details = token_data.get("score", {}).get("details", {})
    checks = details.get("safety", {}).get("checks", {})
    holders = details.get("holders", {})
    deployer = token_data.get("deployer_check", {}).get("stats", {})
    onchain = token_data.get("onchain_metrics", {})
    social = token_data.get("social_sentiment", {})
    price_hist = token_data.get("price_history", {})
    market = token_data.get("market_context", {})
    feedback = token_data.get("feedback_stats", {})

    data_quality = 0
    total_fields = 10

    if details.get("safety", {}).get("score", 0) > 0:
        data_quality += 1
    if details.get("liquidity", {}).get("liquidity_usd", 0) > 0:
        data_quality += 1
    if isinstance(holders.get("total_holders"), (int, float)) and holders.get("total_holders", 0) > 0:
        data_quality += 1
    if deployer.get("status") and deployer.get("status") != "unknown":
        data_quality += 1
    if onchain.get("tx_count_1h", 0) > 0:
        data_quality += 1
    if social.get("social_count", 0) > 0:
        data_quality += 1
    if token_data.get("price_change_24h") is not None:
        data_quality += 1
    if checks.get("honeypot_detected") is not None:
        data_quality += 1
    if price_hist.get("trend") and price_hist.get("trend") != "unknown":
        data_quality += 1
    if market.get("market_mood") and market.get("market_mood") != "unknown":
        data_quality += 1

    quality_pct = data_quality / total_fields

    if quality_pct >= 0.8:
        confidence += 2
    elif quality_pct >= 0.5:
        confidence += 1
    elif quality_pct < 0.3:
        confidence -= 2

    holder_total = holders.get("total_holders", 0)
    if isinstance(holder_total, str):
        holder_total = 0
    if holder_total >= 100:
        confidence += 1
    elif holder_total < 20 and holder_total > 0:
        confidence -= 1

    onchain_momentum = onchain.get("momentum", "unknown")
    if onchain_momentum == "surging":
        confidence += 2
    elif onchain_momentum == "rising":
        confidence += 1
    elif onchain_momentum == "declining":
        confidence -= 1

    trend = price_hist.get("trend", "unknown")
    if trend == "strong_uptrend":
        confidence += 2
    elif trend == "uptrend" or trend == "consistent_up":
        confidence += 1
    elif trend == "strong_downtrend":
        confidence -= 2
    elif trend == "downtrend":
        confidence -= 1

    buy_pressure = price_hist.get("buy_pressure", "unknown")
    if buy_pressure == "very_strong":
        confidence += 2
    elif buy_pressure == "strong":
        confidence += 1
    elif buy_pressure == "weak":
        confidence -= 1
    elif buy_pressure == "very_weak":
        confidence -= 2

    if deployer.get("status") == "trusted":
        confidence += 1
    elif deployer.get("status") == "suspicious":
        confidence -= 2

    social_count = social.get("social_count", 0)
    if social_count >= 3:
        confidence += 1
    elif social_count == 0:
        confidence -= 1

    market_mood = market.get("market_mood", "neutral")
    if market_mood == "very_bullish":
        confidence += 1
    elif market_mood == "very_bearish":
        confidence -= 1

    sm = token_data.get("smart_money", {})
    if sm.get("insider_selling"):
        confidence -= 3
    elif sm.get("smart_holder_count", 0) > 0:
        confidence += min(sm.get("smart_holder_count", 0), 2)
    if sm.get("early_buyer_retention_pct") is not None:
        if sm["early_buyer_retention_pct"] >= 70:
            confidence += 1
        elif sm["early_buyer_retention_pct"] < 30:
            confidence -= 1

    feedback_adj = feedback.get("confidence_adjustment", 0)
    confidence += feedback_adj

    confidence = max(1, min(10, confidence))

    parsed["confidence"] = confidence
    parsed["data_quality"] = round(quality_pct * 100)
    return parsed


def _fallback_response(token_data: Dict, error: str = "") -> Dict:
    pro = token_data.get("professional", {})
    signal = pro.get("signal", "BUY")
    confidence = pro.get("confidence", 5)

    signal_map = {
        "STRONG_BUY": {"target": "+120%", "stop": "-30%"},
        "BUY": {"target": "+80%", "stop": "-40%"},
        "WATCH": {"target": "+40%", "stop": "-50%"},
        "AVOID": {"target": "N/A", "stop": "N/A"},
    }
    defaults = signal_map.get(signal, signal_map["WATCH"])

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": f"Score: {token_data.get('score', {}).get('total_score', 0)}/100. {len(pro.get('positives', []))} strengths, {len(pro.get('concerns', []))} concerns." + (f" (Error: {error})" if error else ""),
        "target_price_pct": defaults["target"],
        "stop_loss_pct": defaults["stop"],
        "risk_level": "medium",
        "position_size": pro.get("position_recommendation", "1-3% portfolio"),
        "source": "fallback" if error else "engine",
        "data_quality": 0,
    }
