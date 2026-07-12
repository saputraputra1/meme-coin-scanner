from typing import Dict
from config import HELIUS_API_KEY
from core.helius import HeliusClient


async def verify_contract_safety(token_address: str) -> Dict:
    client = HeliusClient(HELIUS_API_KEY)
    result = {
        "mint_renounced": False,
        "freeze_disabled": False,
        "lp_burned": False,
        "is_verified": False,
        "mint_authority_address": None,
        "freeze_authority_address": None,
        "lp_burn_address": None,
        "risks": [],
        "score": 0,
    }

    try:
        mint_info = await client.get_mint_info(token_address)
        if mint_info:
            mint_auth = mint_info.get("mint_authority")
            freeze_auth = mint_info.get("freeze_authority")

            if mint_auth is None:
                result["mint_renounced"] = True
                result["score"] += 40
            else:
                result["mint_authority_address"] = str(mint_auth)
                result["risks"].append("Mint authority active")

            if freeze_auth is None:
                result["freeze_disabled"] = True
                result["score"] += 25
            else:
                result["freeze_authority_address"] = str(freeze_auth)
                result["risks"].append("Freeze authority active")

    except Exception:
        pass

    try:
        holders = await client.get_token_largest_holders(token_address, limit=30)
        burn_addresses = [
            "11111111111111111111111111111111",
            "dead1111111111111111111111111111111111111111",
            "burn1111111111111111111111111111111111111111",
        ]

        for h in holders:
            addr = str(h.get("address", "")).lower()
            if any(burn.lower() in addr for burn in burn_addresses):
                result["lp_burned"] = True
                result["lp_burn_address"] = addr
                result["score"] += 20
                break

        if not result["lp_burned"] and len(holders) > 0:
            result["risks"].append("LP not burned")

    except Exception:
        pass

    result["is_verified"] = result["score"] >= 60
    result["risk_level"] = "low" if result["score"] >= 80 else "medium" if result["score"] >= 50 else "high"

    await client.close()
    return result


async def detect_whale_clusters(token_address: str, whale_wallets: list) -> Dict:
    if len(whale_wallets) < 3:
        return {"is_clustered": False, "cluster_count": 0, "risk": "low"}

    client = HeliusClient(HELIUS_API_KEY)
    clusters = []
    funders = {}

    try:
        for whale in whale_wallets[:10]:
            addr = whale.get("wallet", "")
            sigs = await client.get_signatures(addr, limit=3)
            for sig_info in sigs:
                sig = sig_info.get("signature", "")
                tx = await client.get_transaction(sig)
                if not tx:
                    continue
                fee_payer = _get_fee_payer(tx)
                if fee_payer:
                    funders[addr] = fee_payer
                    break

        funder_groups = {}
        for wallet, funder in funders.items():
            if funder not in funder_groups:
                funder_groups[funder] = []
            funder_groups[funder].append(wallet)

        for funder, wallets in funder_groups.items():
            if len(wallets) >= 3:
                clusters.append({
                    "funder": funder[:12] + "...",
                    "wallet_count": len(wallets),
                    "wallets": [w[:8] + "..." for w in wallets[:5]],
                })

        is_clustered = len(clusters) > 0
        risk = "high" if is_clustered else "low"

        return {
            "is_clustered": is_clustered,
            "cluster_count": len(clusters),
            "clusters": clusters,
            "risk": risk,
        }
    except Exception:
        return {"is_clustered": False, "cluster_count": 0, "risk": "unknown"}
    finally:
        await client.close()


def _get_fee_payer(tx_data: dict) -> str:
    msg = tx_data.get("transaction", {}).get("message", {}) or tx_data.get("message", {})
    account_keys = msg.get("accountKeys", [])
    if account_keys and len(account_keys) > 0:
        first = account_keys[0]
        return str(first.get("pubkey", "")) if isinstance(first, dict) else str(first)
    return ""
