from typing import Dict
from config import HELIUS_API_KEY
from core.solscan import get_token_meta


async def check_safety(token_address: str) -> Dict:
    score = 0
    checks = {}

    meta, rug_report, swap_report = await asyncio_gather_three(
        _fetch_meta(token_address),
        _fetch_rugcheck(token_address),
        _fetch_swap(token_address),
    )

    mint_auth = meta.get("mintAuthority") or meta.get("mintAuth") if meta else "unknown"
    freeze_auth = meta.get("freezeAuthority") or meta.get("freezeAuth") if meta else "unknown"
    verified = bool(meta.get("verified", False)) if meta else False

    if mint_auth is None:
        checks["mint_authority"] = True
        score += 8
    elif mint_auth == "unknown":
        checks["mint_authority"] = "unknown"
        score += 4
    else:
        checks["mint_authority"] = False

    if freeze_auth is None:
        checks["freeze_authority"] = True
        score += 5
    elif freeze_auth == "unknown":
        checks["freeze_authority"] = "unknown"
        score += 3
    else:
        checks["freeze_authority"] = False

    checks["verified"] = verified
    if verified:
        score += 5

    if rug_report["success"]:
        rugs = rug_report["data"]
        checks["rugcheck"] = True
        checks["rugcheck_score"] = rugs["score"]
        score += rugs["score"]

        checks["honeypot_detected"] = rugs["is_honeypot"]
        checks["risk_count"] = rugs["total_risks"]
        checks["risk_critical"] = rugs["critical"]
        checks["risk_warnings"] = rugs["warnings"]
        checks["has_lp_risk"] = rugs["has_lp_risk"]
        checks["has_holder_risk"] = rugs["has_holder_risk"]
        checks["has_freeze_risk"] = rugs["has_freeze_risk"]
        checks["risk_items"] = rugs["risk_list"]
        checks["market_type"] = rugs["market_type"]

        if rugs["is_clean"]:
            checks["lp_burned"] = True
            score += 5
        elif rugs["has_lp_risk"]:
            checks["lp_burned"] = False
        else:
            checks["lp_burned"] = True
    else:
        checks["rugcheck"] = False
        checks["lp_burned"] = "unknown"
        checks["honeypot_detected"] = "unknown"
        checks["risk_count"] = "?"
        checks["risk_items"] = []
        score += 15

    if swap_report["success"]:
        checks["swap_sim"] = True
        checks["can_swap"] = swap_report["data"]["can_swap"]
        checks["price_impact"] = swap_report["data"]["price_impact_pct"]
        checks["swap_suspicious"] = swap_report["data"]["is_suspicious"]

        if swap_report["data"]["is_suspicious"]:
            score -= 5
        else:
            score += 7
    else:
        checks["swap_sim"] = False
        checks["can_swap"] = "unknown"
        checks["price_impact"] = "?"
        checks["swap_suspicious"] = "unknown"

    score = max(0, min(100, score))

    if checks.get("honeypot_detected") is True:
        risk = "critical"
    elif score >= 70:
        risk = "low"
    elif score >= 45:
        risk = "medium"
    else:
        risk = "high"

    return {
        "score": score,
        "checks": checks,
        "risk": risk,
    }


async def _fetch_meta(token_address: str) -> Dict | None:
    meta = await get_token_meta(token_address)
    if meta is None:
        meta = await _check_via_helius(token_address)
    return meta


async def _fetch_rugcheck(token_address: str) -> Dict:
    try:
        from core.rugcheck import fetch_rugcheck_report, analyze_rugcheck_report

        report = await fetch_rugcheck_report(token_address)
        if not report:
            return {"success": False}
        return {"success": True, "data": analyze_rugcheck_report(report)}
    except Exception:
        return {"success": False}


async def _fetch_swap(token_address: str) -> Dict:
    try:
        from core.jupiter import swap_check_report

        report = await swap_check_report(token_address)
        return {"success": True, "data": report}
    except Exception:
        return {"success": False}


async def asyncio_gather_three(task_a, task_b, task_c):
    import asyncio
    results = await asyncio.gather(task_a, task_b, task_c, return_exceptions=True)

    def unwrap(r):
        if isinstance(r, BaseException):
            return None
        return r

    return unwrap(results[0]), unwrap(results[1]), unwrap(results[2])


async def _check_via_helius(token_address: str) -> Dict | None:
    from core.helius import HeliusClient

    client = HeliusClient(HELIUS_API_KEY)
    try:
        mint_info = await client.get_mint_info(token_address)
        if not mint_info:
            return None

        mint_auth = mint_info.get("mint_authority") or mint_info.get("mintAuthority")
        freeze_auth = mint_info.get("freeze_authority") or mint_info.get("freezeAuthority")

        return {
            "mintAuthority": mint_auth,
            "freezeAuthority": freeze_auth,
            "isMutable": None,
            "verified": False,
        }
    except Exception:
        return None
    finally:
        await client.close()
