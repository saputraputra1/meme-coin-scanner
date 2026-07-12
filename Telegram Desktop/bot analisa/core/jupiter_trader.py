import base64
import json
from typing import Dict, Optional
from utils.client import HttpClient
from core.helius import HeliusClient
from config import HELIUS_API_KEY

JUPITER_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP = "https://quote-api.jup.ag/v6/swap"
SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


async def get_quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int = 500) -> Optional[Dict]:
    client = await HttpClient.get_instance()
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": slippage_bps,
    }
    try:
        data = await client.get(JUPITER_QUOTE, params=params)
        if not data or "error" in data:
            return None
        return data
    except Exception:
        return None


async def execute_swap(quote: Dict, wallet_private_key: str) -> Optional[Dict]:
    client = await HttpClient.get_instance()

    try:
        from solders.keypair import Keypair
        if len(wallet_private_key) == 64:
            key_bytes = bytes.fromhex(wallet_private_key)
        else:
            key_bytes = base64.b64decode(wallet_private_key)
        kp = Keypair.from_bytes(key_bytes)
    except Exception:
        return {"success": False, "error": "Invalid private key"}

    try:
        swap_data = await client.post(
            JUPITER_SWAP,
            json_data={
                "quoteResponse": quote,
                "userPublicKey": str(kp.pubkey()),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto",
            },
        )
    except Exception as e:
        return {"success": False, "error": f"Swap API error: {str(e)[:100]}"}

    if not swap_data or "error" in swap_data:
        return {"success": False, "error": str(swap_data.get("error", "Unknown error"))}

    swap_tx = swap_data.get("swapTransaction")
    if not swap_tx:
        return {"success": False, "error": "No swap transaction returned"}

    try:
        tx_bytes = base64.b64decode(swap_tx)
        from solders.transaction import VersionedTransaction
        tx = VersionedTransaction.from_bytes(tx_bytes)

        signed_tx = VersionedTransaction(tx.message, [kp])
        signed_bytes = bytes(signed_tx)
        signed_b64 = base64.b64encode(signed_bytes).decode()
    except Exception as e:
        return {"success": False, "error": f"Sign error: {str(e)[:100]}"}

    helius = HeliusClient(HELIUS_API_KEY)
    try:
        result = await helius._call("sendTransaction", [
            signed_b64,
            {"encoding": "base64", "skipPreflight": True, "maxRetries": 3},
        ])

        tx_hash = result.get("result")
        if tx_hash:
            return {"success": True, "tx_hash": tx_hash, "quote": quote}
        else:
            error = result.get("error", {})
            return {"success": False, "error": str(error)[:200]}
    except Exception as e:
        return {"success": False, "error": f"Send error: {str(e)[:100]}"}
    finally:
        await helius.close()


async def buy_token(token_address: str, amount_sol: float, slippage_bps: int = 500, wallet_private_key: str = "") -> Dict:
    amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)

    quote = await get_quote(SOL_MINT, token_address, amount_lamports, slippage_bps)
    if not quote:
        return {"success": False, "error": "No route found or insufficient liquidity"}

    price_impact = float(quote.get("priceImpactPct", 100) or 100)
    if price_impact > 25:
        return {"success": False, "error": f"Price impact too high: {price_impact:.1f}%"}

    result = await execute_swap(quote, wallet_private_key)
    if result.get("success"):
        out_amount = int(quote.get("outAmount", 0))
        in_amount = int(quote.get("inAmount", 0))
        result["in_amount_sol"] = in_amount / LAMPORTS_PER_SOL
        result["out_amount_tokens"] = out_amount
        result["price_impact"] = price_impact

    return result


async def sell_token(token_address: str, token_amount: int, slippage_bps: int = 500, wallet_private_key: str = "") -> Dict:
    quote = await get_quote(token_address, SOL_MINT, token_amount, slippage_bps)
    if not quote:
        return {"success": False, "error": "No route found for sell"}

    result = await execute_swap(quote, wallet_private_key)
    if result.get("success"):
        out_amount = int(quote.get("outAmount", 0))
        result["out_amount_sol"] = out_amount / LAMPORTS_PER_SOL
        result["in_amount_tokens"] = token_amount

    return result


async def sell_token_by_sol_value(token_address: str, percentage: float, slippage_bps: int = 500, wallet_private_key: str = "") -> Dict:
    helius = HeliusClient(HELIUS_API_KEY)
    try:
        from solders.keypair import Keypair
        if len(wallet_private_key) == 64:
            key_bytes = bytes.fromhex(wallet_private_key)
        else:
            key_bytes = base64.b64decode(wallet_private_key)
        kp = Keypair.from_bytes(key_bytes)
        address = str(kp.pubkey())
    except Exception:
        return {"success": False, "error": "Invalid private key"}

    try:
        balance = await helius.get_token_balance(address, token_address)
        if not balance or balance.get("ui_amount", 0) <= 0:
            return {"success": False, "error": "No token balance"}

        amount = int(balance.get("amount", "0"))
        sell_amount = int(amount * percentage)
        if sell_amount <= 0:
            return {"success": False, "error": "Insufficient balance"}

        return await sell_token(token_address, sell_amount, slippage_bps, wallet_private_key)
    finally:
        await helius.close()
