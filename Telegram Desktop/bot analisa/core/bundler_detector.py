from datetime import datetime, timezone
from typing import Dict, List
from config import HELIUS_API_KEY
from core.helius import HeliusClient


async def detect_bundler_activity(token_address: str) -> Dict:
    client = HeliusClient(HELIUS_API_KEY)
    try:
        sigs = await client.get_signatures(token_address, limit=30)

        if not sigs:
            return {"checked": False, "reason": "No signatures found"}

        earliest_sigs = list(reversed(sigs))
        unique_buyers = set()
        rapid_buys = 0
        bundled_wallets = []
        first_tx_time = None

        for sig_item in earliest_sigs[:20]:
            sig = sig_item.get("signature", "")
            tx_time = sig_item.get("blockTime", 0)

            if tx_time and first_tx_time is None:
                first_tx_time = datetime.fromtimestamp(tx_time, tz=timezone.utc)

            if tx_time and first_tx_time:
                elapsed = datetime.fromtimestamp(tx_time, tz=timezone.utc) - first_tx_time
                if elapsed.total_seconds() > 300:
                    break

            tx_data = await client.get_transaction(sig)
            if not tx_data:
                continue

            instructions = _extract_instructions(tx_data)
            for inst in instructions:
                if inst.get("type") == "transfer" and inst.get("to") == token_address:
                    continue
                if inst.get("type") == "buy":
                    buyer = inst.get("buyer", "")
                    if buyer and buyer not in unique_buyers:
                        unique_buyers.add(buyer)
                        if elapsed.total_seconds() < 60 if first_tx_time and tx_time else True:
                            rapid_buys += 1
                            bundled_wallets.append(buyer[:8] + "...")

        is_suspicious = rapid_buys >= 5 and len(unique_buyers) >= 4
        concentration = rapid_buys

        return {
            "checked": True,
            "unique_buyers_first_5min": len(unique_buyers),
            "rapid_buys_under_60s": rapid_buys,
            "is_bundled": is_suspicious,
            "suspicious_wallets_count": concentration,
            "risk": "high" if is_suspicious else "low" if rapid_buys > 0 else "none",
            "wallet_previews": bundled_wallets[:5],
        }
    except Exception as e:
        return {"checked": False, "reason": str(e)[:100]}
    finally:
        await client.close()


def _extract_instructions(tx_data: dict) -> List[Dict]:
    instructions = []

    meta = tx_data.get("meta", {})
    message = tx_data.get("transaction", {}).get("message", {}) or tx_data.get("message", {})

    account_keys = message.get("accountKeys", [])
    if isinstance(account_keys, dict):
        account_keys = []

    inner_instructions = meta.get("innerInstructions", [])

    found_token_transfers = []
    for inner in inner_instructions:
        for ix in inner.get("instructions", []):
            parsed = ix.get("parsed", {})
            if parsed.get("type") == "transfer":
                info = parsed.get("info", {})
                found_token_transfers.append({
                    "type": "transfer",
                    "from": info.get("authority", ""),
                    "to": info.get("destination", ""),
                    "amount": info.get("amount", "0"),
                })

    if found_token_transfers:
        return found_token_transfers

    for ix in message.get("instructions", []) if isinstance(message, dict) else []:
        parsed = ix.get("parsed", {})
        ixtype = parsed.get("type", ix.get("programId", ""))

        if ixtype == "transfer":
            info = parsed.get("info", {})
            buyer = info.get("authority", info.get("source", ""))
            instructions.append({
                "type": "buy",
                "buyer": buyer,
                "amount": info.get("amount", "0"),
            })

    return instructions or [{"type": "unknown"}]
