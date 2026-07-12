from datetime import datetime, timezone
from typing import Dict, List
from config import HELIUS_API_KEY
from core.helius import HeliusClient


async def get_onchain_metrics(token_address: str) -> Dict:
    client = HeliusClient(HELIUS_API_KEY)
    try:
        sigs = await client.get_signatures(token_address, limit=50)
        if not sigs:
            return _empty_metrics()

        now = datetime.now(timezone.utc)
        h1_sigs = []
        h6_sigs = []
        h24_sigs = []
        all_sigs = []

        for sig_info in sigs:
            block_time = sig_info.get("blockTime", 0)
            if not block_time:
                continue
            tx_time = datetime.fromtimestamp(block_time, tz=timezone.utc)
            age_hours = (now - tx_time).total_seconds() / 3600

            all_sigs.append(sig_info)
            if age_hours <= 1:
                h1_sigs.append(sig_info)
            if age_hours <= 6:
                h6_sigs.append(sig_info)
            if age_hours <= 24:
                h24_sigs.append(sig_info)

        unique_buyers_1h = set()
        unique_sellers_1h = set()
        total_buy_amount = 0
        total_sell_amount = 0
        whale_txs = 0

        for sig_info in h1_sigs[:10]:
            sig = sig_info.get("signature", "")
            tx = await client.get_transaction(sig)
            if not tx:
                continue

            buys, sells = _analyze_transaction(tx, token_address)
            for b in buys:
                unique_buyers_1h.add(b["wallet"])
                total_buy_amount += b["amount"]
                if b["amount"] > 1000:
                    whale_txs += 1
            for s in sells:
                unique_sellers_1h.add(s["wallet"])
                total_sell_amount += s["amount"]
                if s["amount"] > 1000:
                    whale_txs += 1

        buyer_seller_ratio = len(unique_buyers_1h) / max(len(unique_sellers_1h), 1)

        return {
            "tx_count_1h": len(h1_sigs),
            "tx_count_6h": len(h6_sigs),
            "tx_count_24h": len(h24_sigs),
            "unique_buyers_1h": len(unique_buyers_1h),
            "unique_sellers_1h": len(unique_sellers_1h),
            "buyer_seller_ratio": round(buyer_seller_ratio, 2),
            "total_buy_amount": total_buy_amount,
            "total_sell_amount": total_sell_amount,
            "whale_tx_count": whale_txs,
            "momentum": _calculate_momentum(len(h1_sigs), len(h6_sigs), len(h24_sigs)),
        }
    except Exception:
        return _empty_metrics()
    finally:
        await client.close()


def _analyze_transaction(tx_data: dict, token_address: str) -> tuple:
    buys = []
    sells = []

    meta = tx_data.get("meta", {})
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])

    account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
    fee_payer = ""
    if account_keys:
        first_key = account_keys[0]
        fee_payer = str(first_key.get("pubkey", "")) if isinstance(first_key, dict) else str(first_key)

    for post in post_balances:
        mint = post.get("mint", "")
        if mint != token_address:
            continue

        owner = post.get("owner", "")
        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

        pre_amount = 0
        for pre in pre_balances:
            if pre.get("mint") == mint and pre.get("owner") == owner:
                pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                break

        if post_amount > pre_amount:
            buys.append({"wallet": owner, "amount": post_amount - pre_amount})
        elif pre_amount > post_amount:
            sells.append({"wallet": owner, "amount": pre_amount - post_amount})

    return buys, sells


def _calculate_momentum(h1: int, h6: int, h24: int) -> str:
    if h24 == 0:
        return "none"

    h1_per_hour = h1
    h6_per_hour = h6 / 6
    h24_per_hour = h24 / 24

    if h1_per_hour > h6_per_hour * 2 and h1_per_hour > h24_per_hour * 3:
        return "surging"
    elif h1_per_hour > h6_per_hour * 1.5:
        return "rising"
    elif h1_per_hour < h24_per_hour * 0.5:
        return "declining"
    else:
        return "stable"


def _empty_metrics() -> Dict:
    return {
        "tx_count_1h": 0,
        "tx_count_6h": 0,
        "tx_count_24h": 0,
        "unique_buyers_1h": 0,
        "unique_sellers_1h": 0,
        "buyer_seller_ratio": 0,
        "total_buy_amount": 0,
        "total_sell_amount": 0,
        "whale_tx_count": 0,
        "momentum": "unknown",
    }
