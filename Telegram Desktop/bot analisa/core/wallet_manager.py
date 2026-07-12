import json
import os
import base64
import hashlib
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timezone

from config import HELIUS_API_KEY
from core.helius import HeliusClient

WALLETS_FILE = Path(__file__).parent.parent / "data" / "wallets.json"
ENCRYPTION_KEY = os.environ.get("WALLET_ENC_KEY", "meme-scanner-2026-default-key")


def _derive_key(password: str) -> bytes:
    return hashlib.sha256(password.encode()).digest()


def encrypt_private_key(private_key: str, password: str = ENCRYPTION_KEY) -> str:
    key = _derive_key(password)
    encrypted = bytearray()
    for i, byte in enumerate(private_key.encode()):
        encrypted.append(byte ^ key[i % len(key)])
    return base64.b64encode(bytes(encrypted)).decode()


def decrypt_private_key(encrypted_key: str, password: str = ENCRYPTION_KEY) -> str:
    key = _derive_key(password)
    encrypted = base64.b64decode(encrypted_key)
    decrypted = bytearray()
    for i, byte in enumerate(encrypted):
        decrypted.append(byte ^ key[i % len(key)])
    return bytes(decrypted).decode()


def load_wallets() -> List[Dict]:
    if WALLETS_FILE.exists():
        try:
            return json.loads(WALLETS_FILE.read_text())
        except Exception:
            return []
    return []


def save_wallets(wallets: List[Dict]):
    WALLETS_FILE.parent.mkdir(exist_ok=True, parents=True)
    WALLETS_FILE.write_text(json.dumps(wallets, indent=2, ensure_ascii=False))


def link_wallet(chat_id: str, private_key: str) -> Dict:
    wallets = load_wallets()

    address = _get_address_from_key(private_key)
    if not address:
        return {"success": False, "error": "Invalid private key"}

    encrypted_key = encrypt_private_key(private_key)

    for w in wallets:
        if w.get("chat_id") == chat_id:
            w["wallet_address"] = address
            w["private_key_encrypted"] = encrypted_key
            w["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_wallets(wallets)
            return {"success": True, "address": address}

    wallet_entry = {
        "chat_id": chat_id,
        "wallet_address": address,
        "private_key_encrypted": encrypted_key,
        "linked_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "auto_trade_enabled": False,
        "trade_mode": "full-auto",
        "buy_amount_sol": 0.1,
        "max_positions": 5,
        "stop_loss_pct": -40,
        "take_profit_pct": 100,
        "slippage_bps": 500,
    }
    wallets.append(wallet_entry)
    save_wallets(wallets)
    return {"success": True, "address": address}


def unlink_wallet(chat_id: str) -> bool:
    wallets = load_wallets()
    new_wallets = [w for w in wallets if w.get("chat_id") != chat_id]
    if len(new_wallets) < len(wallets):
        save_wallets(new_wallets)
        return True
    return False


def get_wallet(chat_id: str) -> Optional[Dict]:
    wallets = load_wallets()
    for w in wallets:
        if w.get("chat_id") == chat_id:
            return w
    return None


def update_wallet_config(chat_id: str, updates: Dict) -> bool:
    wallets = load_wallets()
    for w in wallets:
        if w.get("chat_id") == chat_id:
            w.update(updates)
            w["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_wallets(wallets)
            return True
    return False


def get_decrypted_key(chat_id: str) -> Optional[str]:
    wallet = get_wallet(chat_id)
    if not wallet:
        return None
    try:
        return decrypt_private_key(wallet["private_key_encrypted"])
    except Exception:
        return None


async def get_wallet_balance(chat_id: str) -> Optional[Dict]:
    wallet = get_wallet(chat_id)
    if not wallet:
        return None

    address = wallet["wallet_address"]
    client = HeliusClient(HELIUS_API_KEY)
    try:
        sol_balance = await client.get_balance(address)
        token_accounts = await client.get_token_accounts(address)

        tokens = []
        for acc in token_accounts:
            parsed = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            ui_amount = parsed.get("tokenAmount", {}).get("uiAmount", 0) or 0
            if ui_amount > 0:
                tokens.append({
                    "mint": parsed.get("mint", ""),
                    "amount": ui_amount,
                })

        return {
            "address": address,
            "sol_balance": round(sol_balance or 0, 4),
            "token_count": len(tokens),
            "tokens": tokens[:10],
        }
    except Exception:
        return {"address": address, "sol_balance": 0, "token_count": 0, "tokens": []}
    finally:
        await client.close()


def _get_address_from_key(private_key: str) -> Optional[str]:
    from solders.keypair import Keypair

    key = private_key.strip().strip("[]")

    errors = []

    # 1. Try JSON array format: [123,45,67,...]
    if "," in key:
        try:
            nums = [int(x.strip()) for x in key.split(",") if x.strip().isdigit()]
            if len(nums) == 64:
                kp = Keypair.from_bytes(bytes(nums))
                return str(kp.pubkey())
        except Exception as e:
            errors.append(f"array: {e}")

    # 2. Try hex format (64 chars)
    if len(key) == 64:
        try:
            key_bytes = bytes.fromhex(key)
            kp = Keypair.from_bytes(key_bytes)
            return str(kp.pubkey())
        except Exception as e:
            errors.append(f"hex: {e}")

    # 3. Try base64 format
    try:
        key_bytes = base64.b64decode(key)
        if len(key_bytes) == 64:
            kp = Keypair.from_bytes(key_bytes)
            return str(kp.pubkey())
    except Exception as e:
        errors.append(f"b64: {e}")

    # 4. Try base58 format (Phantom/Solflare standard)
    try:
        import base58
        key_bytes = base58.b58decode(key)
        if len(key_bytes) == 64:
            kp = Keypair.from_bytes(key_bytes)
            return str(kp.pubkey())
    except Exception as e:
        errors.append(f"b58: {e}")

    # 5. Try with base58 prefix
    try:
        clean = key.replace("[", "").replace("]", "").replace("\"", "").replace("'", "")
        if len(clean) >= 80:
            import base58
            key_bytes = base58.b58decode(clean)
            if len(key_bytes) == 64:
                kp = Keypair.from_bytes(key_bytes)
                return str(kp.pubkey())
    except Exception as e:
        errors.append(f"b58_clean: {e}")

    return None


def get_all_active_wallets() -> List[Dict]:
    wallets = load_wallets()
    return [w for w in wallets if w.get("auto_trade_enabled")]
