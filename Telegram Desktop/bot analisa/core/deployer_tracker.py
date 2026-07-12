import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
from config import HELIUS_API_KEY
from core.helius import HeliusClient

DEPLOYER_LIST_FILE = Path(__file__).parent.parent / "data" / "deployer_watchlist.json"


def load_deployer_list() -> List[Dict]:
    if DEPLOYER_LIST_FILE.exists():
        try:
            return json.loads(DEPLOYER_LIST_FILE.read_text())
        except Exception:
            return []
    return []


def save_deployer_list(items: List[Dict]):
    DEPLOYER_LIST_FILE.parent.mkdir(exist_ok=True, parents=True)
    DEPLOYER_LIST_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False))


def add_deployer(address: str, name: str = "", note: str = "") -> Dict:
    items = load_deployer_list()
    for item in items:
        if item["address"] == address:
            return item

    deployer = {
        "address": address,
        "name": name or f"Deployer {address[:8]}",
        "note": note,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "last_scanned": None,
        "tokens_deployed": [],
    }
    items.append(deployer)
    save_deployer_list(items)
    return deployer


def remove_deployer(address: str) -> bool:
    items = load_deployer_list()
    new_items = [i for i in items if i["address"] != address]
    if len(new_items) < len(items):
        save_deployer_list(new_items)
        return True
    return False


async def scan_deployer_new_tokens() -> List[Dict]:
    deployers = load_deployer_list()
    if not deployers:
        return []

    client = HeliusClient(HELIUS_API_KEY)
    alerts = []

    try:
        for dep in deployers[:5]:
            addr = dep["address"]
            known_tokens = dep.get("tokens_deployed", [])

            sigs = await client.get_signatures(addr, limit=20)
            for sig_info in sigs:
                sig = sig_info.get("signature", "")
                tx = await client.get_transaction(sig)
                if not tx:
                    continue

                new_mints = _extract_mints_from_tx(tx)
                for mint in new_mints:
                    if mint not in known_tokens:
                        known_tokens.append(mint)
                        alerts.append({
                            "deployer": addr,
                            "deployer_name": dep.get("name", addr[:8]),
                            "token_mint": mint,
                            "signature": sig[:12] + "...",
                            "time": sig_info.get("blockTime", 0),
                            "total_deployed": dep.get("total_deployed", 0) + 1,
                        })

            dep["tokens_deployed"] = known_tokens[-20:]
            dep["total_deployed"] = len(known_tokens)
            dep["last_scanned"] = datetime.now(timezone.utc).isoformat()
    finally:
        await client.close()

    if alerts:
        save_deployer_list(deployers)

    return alerts


def _extract_mints_from_tx(tx_data: dict) -> List[str]:
    mints = []

    meta = tx_data.get("meta", {})
    for token_balance in (meta.get("postTokenBalances", []) or []):
        mint = token_balance.get("mint", "")
        if mint:
            mints.add(mint)

    msg = tx_data.get("transaction", {}).get("message", {}) or tx_data.get("message", {})
    for ix in (msg.get("instructions", []) or []):
        parsed = ix.get("parsed", {})
        info = parsed.get("info", {})
        mint_from_info = info.get("mint", info.get("mintAddress", ""))
        if mint_from_info:
            mints.append(str(mint_from_info))

    return list(set(mints))
