import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
from config import HELIUS_API_KEY
from core.helius import HeliusClient

DEPLOYER_CACHE = Path(__file__).parent.parent / "data" / "deployer_cache.json"
CACHE_TTL_DAYS = 3


def load_cache() -> Dict:
    if DEPLOYER_CACHE.exists():
        try:
            return json.loads(DEPLOYER_CACHE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: Dict):
    DEPLOYER_CACHE.parent.mkdir(exist_ok=True, parents=True)
    DEPLOYER_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


async def find_creator_wallet(token_address: str) -> Optional[str]:
    client = HeliusClient(HELIUS_API_KEY)
    try:
        sigs = await client.get_signatures(token_address, limit=5)
        if not sigs:
            return None

        first_sig = sigs[-1].get("signature", "") if len(sigs) > 0 else sigs[0].get("signature", "")
        if not first_sig:
            return None

        tx = await client.get_transaction(first_sig)
        if not tx:
            return None

        message = tx.get("transaction", {}).get("message", {}) or tx.get("message", {})
        account_keys = message.get("accountKeys", [])

        if isinstance(account_keys, list) and len(account_keys) > 0:
            first_key = account_keys[0]
            if isinstance(first_key, dict):
                return str(first_key.get("pubkey", ""))
            return str(first_key)

        return None
    except Exception:
        return None
    finally:
        await client.close()


async def get_deployer_stats(wallet_address: str) -> Dict:
    cache = load_cache()
    key = wallet_address

    if key in cache:
        entry = cache[key]
        last_updated = entry.get("last_updated", "")
        if last_updated:
            try:
                last = datetime.fromisoformat(last_updated)
                if (datetime.now(timezone.utc) - last).days < CACHE_TTL_DAYS:
                    return entry
            except Exception:
                pass

    client = HeliusClient(HELIUS_API_KEY)
    try:
        sigs = await client.get_signatures(wallet_address, limit=30)

        token_creations = []
        related_tokens = set()

        for sig_info in sigs:
            sig = sig_info.get("signature", "")
            tx = await client.get_transaction(sig)
            if not tx:
                continue

            msg = tx.get("transaction", {}).get("message", {}) or tx.get("message", {})
            instructions = msg.get("instructions", [])

            for ix in instructions:
                program_id = ix.get("programId", "")
                parsed = ix.get("parsed", {})

                if "Token" in str(program_id) or "token" in str(program_id).lower():
                    info = parsed.get("info", {})
                    mint = info.get("mint", info.get("mintAddress", ""))
                    if mint:
                        related_tokens.add(str(mint))
                        token_creations.append({
                            "mint": str(mint),
                            "time": sig_info.get("blockTime", 0),
                        })

        from core.rugcheck import fetch_rugcheck_report, analyze_rugcheck_report

        success_count = 0
        rug_count = 0
        unknown_count = 0
        total_checked = 0

        for mint in list(related_tokens)[:5]:
            total_checked += 1
            try:
                report = await fetch_rugcheck_report(mint)
                if report:
                    result = analyze_rugcheck_report(report)
                    if result.get("is_clean") or result.get("total_risks", 0) == 0:
                        success_count += 1
                    elif result.get("is_honeypot"):
                        rug_count += 1
                else:
                    unknown_count += 1
            except Exception:
                unknown_count += 1

        total_known = total_checked
        success_rate = (success_count / total_known * 100) if total_known > 0 else 0
        rug_rate = (rug_count / total_known * 100) if total_known > 0 else 0

        from core.rug_history import check_deployer_rug_history
        rug_hist = check_deployer_rug_history(wallet_address)
        db_rug_count = rug_hist.get("total_rugs", 0)
        total_rugs = rug_count + db_rug_count

        reputation = _calculate_reputation_score(
            total_tokens=len(related_tokens),
            success_rate=success_rate,
            rug_count=total_rugs,
            total_checked=total_known,
        )

        result = {
            "wallet": wallet_address,
            "total_tokens_found": len(related_tokens),
            "tokens_checked": total_known,
            "successful": success_count,
            "rug_count": total_rugs,
            "unknown_count": unknown_count,
            "success_rate": round(success_rate, 1),
            "rug_rate": round(rug_rate, 1),
            "status": reputation["label"],
            "reputation_score": reputation["score"],
            "recent_tokens": [t["mint"] for t in token_creations[:5]],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        cache[key] = result
        save_cache(cache)
        return result

    except Exception as e:
        return {
            "wallet": wallet_address,
            "total_tokens_found": 0,
            "tokens_checked": 0,
            "successful": 0,
            "rug_count": 0,
            "unknown_count": 0,
            "success_rate": 0,
            "rug_rate": 0,
            "status": "error",
            "error": str(e)[:100],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await client.close()


async def analyze_token_deployer(token_address: str) -> Dict:
    creator = await find_creator_wallet(token_address)
    if not creator:
        return {"found": False, "creator": None}

    stats = await get_deployer_stats(creator)
    return {
        "found": True,
        "creator": creator,
        "stats": stats,
    }


REPUTATION_LABELS = {
    (80, 100): ("TRUSTED", "✅", "0"),
    (60, 79): ("RELIABLE", "🟢", "1"),
    (40, 59): ("NEUTRAL", "🟡", "2"),
    (20, 39): ("CAUTION", "🟠", "3"),
    (0, 19): ("HIGH RISK", "🔴", "4"),
}


def reputation_label(score: int) -> tuple:
    for (lo, hi), (label, emoji, level) in REPUTATION_LABELS.items():
        if lo <= score <= hi:
            return label, emoji, level
    return "UNKNOWN", "❓", "9"


def _calculate_reputation_score(total_tokens: int, success_rate: float,
                                 rug_count: int, total_checked: int) -> Dict:
    score = 50

    if total_tokens >= 30:
        score += 15
    elif total_tokens >= 10:
        score += 10
    elif total_tokens >= 5:
        score += 5
    elif total_tokens < 3 and total_checked > 0:
        score -= 15

    if success_rate >= 90:
        score += 20
    elif success_rate >= 70:
        score += 10
    elif success_rate >= 50:
        score += 0
    elif total_checked > 0:
        score -= 10

    if rug_count == 0:
        score += 5
    elif rug_count == 1:
        score -= 25
    elif rug_count <= 3:
        score -= 35
    else:
        score -= 50

    if total_tokens > 0 and total_checked > 0 and success_rate >= 80 and rug_count == 0:
        score = max(score, 75)

    if total_tokens == 0 and total_checked == 0:
        score = 30

    score = max(0, min(100, score))
    label, emoji, level = reputation_label(score)

    return {
        "score": score,
        "label": label,
        "emoji": emoji,
        "level": level,
    }
