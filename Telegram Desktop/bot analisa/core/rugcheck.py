from typing import Dict, List, Optional
from utils.client import HttpClient

RUGCHECK_BASE = "https://api.rugcheck.xyz/v1"


async def fetch_rugcheck_report(token_address: str) -> Optional[Dict]:
    client = await HttpClient.get_instance()
    try:
        data = await client.get(f"{RUGCHECK_BASE}/tokens/{token_address}/report")
        if isinstance(data, dict) and "error" not in data:
            return data
    except Exception:
        pass
    return None


def analyze_rugcheck_report(report: Dict) -> Dict:
    risks = report.get("risks", []) if isinstance(report, dict) else []

    crit_count = 0
    warn_count = 0
    risk_names = []
    is_honeypot = False
    has_lp_risk = False
    has_holder_risk = False
    has_freeze_risk = False

    for r in risks:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name", ""))
        level = str(r.get("level", "")).lower()
        desc = str(r.get("description", ""))

        risk_names.append({"name": name, "level": level, "desc": desc})

        if level == "crit":
            crit_count += 1
        elif level in ("warn", "warning"):
            warn_count += 1

        name_lower = name.lower()
        if "honeypot" in name_lower or "not sellable" in name_lower or "not tradable" in name_lower:
            is_honeypot = True
        if "lp" in name_lower or "liquidity" in name_lower:
            has_lp_risk = True
        if "holder" in name_lower or "top" in name_lower or "ownership" in name_lower:
            has_holder_risk = True
        if "freeze" in name_lower or "mint" in name_lower:
            has_freeze_risk = True

    markets = report.get("markets", []) if isinstance(report, dict) else []
    has_market = len(markets) > 0
    market_type = markets[0].get("marketType", "none") if markets else "none"

    total_risks = len(risks)
    is_clean = total_risks == 0

    score = 100
    if is_honeypot:
        score = 0
    else:
        score -= crit_count * 30
        score -= warn_count * 10
        score = max(0, score)

    return {
        "score": score,
        "total_risks": total_risks,
        "critical": crit_count,
        "warnings": warn_count,
        "is_honeypot": is_honeypot,
        "is_clean": is_clean,
        "has_market": has_market,
        "market_type": market_type,
        "has_lp_risk": has_lp_risk,
        "has_holder_risk": has_holder_risk,
        "has_freeze_risk": has_freeze_risk,
        "risk_list": [r["name"] for r in risk_names],
        "risk_details": risk_names,
    }
