import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger("memecoin-bot")


async def execute_buy(chat_id: str, token_address: str, symbol: str, amount_sol: float,
                      entry_price: float = 0, auto: bool = False) -> Dict:
    from core.wallet_manager import get_wallet, get_decrypted_key
    from core.jupiter_trader import buy_token
    from core.position_tracker import add_position, get_open_positions
    from core.advanced_trader import is_token_cooled_down, set_token_cooldown, load_trade_config

    wallet = get_wallet(chat_id)
    if not wallet:
        return {"success": False, "error": "Wallet not linked. Use /wallet link <private_key>"}

    if not wallet.get("auto_trade_enabled") and auto:
        return {"success": False, "error": "Auto trade disabled. Use /autotrade on"}

    config = load_trade_config(chat_id)

    if auto and config.get("cooldown_enabled", True):
        cooldown_hours = config.get("cooldown_hours", 6)
        if not is_token_cooled_down(token_address, chat_id, cooldown_hours):
            return {"success": False, "error": f"Token in cooldown ({cooldown_hours}h)"}

    open_positions = get_open_positions(chat_id)
    max_positions = wallet.get("max_positions", 5)
    if len(open_positions) >= max_positions:
        return {"success": False, "error": f"Max {max_positions} open positions reached"}

    for pos in open_positions:
        if pos["token_address"] == token_address:
            return {"success": False, "error": f"Already holding {symbol}"}

    private_key = get_decrypted_key(chat_id)
    if not private_key:
        return {"success": False, "error": "Cannot decrypt wallet key"}

    slippage = wallet.get("slippage_bps", 500)

    result = await buy_token(token_address, amount_sol, slippage, private_key)

    if result.get("success"):
        out_tokens = result.get("out_amount_tokens", 0)
        price_impact = result.get("price_impact", 0)
        tx_hash = result.get("tx_hash", "")

        if entry_price == 0 and amount_sol > 0 and out_tokens > 0:
            entry_price = amount_sol / out_tokens if out_tokens > 0 else 0

        position = add_position(
            chat_id=chat_id,
            token_address=token_address,
            symbol=symbol,
            entry_price=entry_price,
            amount_sol=amount_sol,
            amount_tokens=out_tokens,
            tx_hash=tx_hash,
        )

        return {
            "success": True,
            "position": position,
            "tx_hash": tx_hash,
            "amount_sol": amount_sol,
            "amount_tokens": out_tokens,
            "price_impact": price_impact,
        }

    return {"success": False, "error": result.get("error", "Unknown error")}


async def execute_sell(chat_id: str, token_address: str, percentage: float = 1.0) -> Dict:
    from core.wallet_manager import get_wallet, get_decrypted_key
    from core.jupiter_trader import sell_token_by_sol_value
    from core.position_tracker import get_position, close_position
    from core.dexscreener import get_token_info

    wallet = get_wallet(chat_id)
    if not wallet:
        return {"success": False, "error": "Wallet not linked"}

    private_key = get_decrypted_key(chat_id)
    if not private_key:
        return {"success": False, "error": "Cannot decrypt wallet key"}

    position = get_position(token_address, chat_id)
    if not position:
        return {"success": False, "error": "No open position for this token"}

    slippage = wallet.get("slippage_bps", 500)

    result = await sell_token_by_sol_value(token_address, percentage, slippage, private_key)

    if result.get("success"):
        info = await get_token_info(token_address)
        exit_price = info.get("price_usd", 0) if info else 0

        reason = "manual_sell"
        if percentage < 1.0:
            reason = f"partial_sell_{int(percentage*100)}%"

        closed = close_position(position["id"], exit_price, result.get("tx_hash", ""), reason)

        return {
            "success": True,
            "position": closed,
            "tx_hash": result.get("tx_hash", ""),
            "amount_sol_out": result.get("out_amount_sol", 0),
            "percentage": percentage,
        }

    return {"success": False, "error": result.get("error", "Sell failed")}


async def auto_buy_signal(chat_id: str, token_data: Dict, ai_result: Dict) -> Optional[Dict]:
    from core.wallet_manager import get_wallet
    from core.advanced_trader import get_dynamic_buy_amount, load_trade_config

    wallet = get_wallet(chat_id)
    if not wallet:
        return None

    if not wallet.get("auto_trade_enabled"):
        return None

    signal = ai_result.get("signal", "WATCH")
    confidence = ai_result.get("confidence", 0)
    min_confidence = 7

    if signal not in ("STRONG_BUY", "BUY"):
        return None
    if confidence < min_confidence:
        return None

    # Fix #5: require the rule-based engine (analyzers/professional.py) to
    # also agree it's a buy. Previously only "not AVOID" was required before
    # calling the AI, which let the AI's single, occasionally-fragile signal
    # be the sole gate on spending real SOL. Now both must independently say buy.
    rule_signal = token_data.get("professional", {}).get("signal", "WATCH")
    if rule_signal not in ("STRONG_BUY", "BUY"):
        logger.info(
            f"Auto buy skipped for {token_data.get('symbol', '?')}: "
            f"AI said {signal} but rule engine said {rule_signal} (disagreement)"
        )
        return None

    config = load_trade_config(chat_id)
    token_address = token_data.get("token_address", "")
    symbol = token_data.get("symbol", "?")

    if config.get("dynamic_buy_enabled", True):
        amount_sol = get_dynamic_buy_amount(confidence, wallet.get("buy_amount_sol", 0.1))
    else:
        amount_sol = wallet.get("buy_amount_sol", 0.1)

    entry_price = token_data.get("price_usd", 0)

    logger.info(f"Auto buy: {symbol} ({signal}, {confidence}/10, {amount_sol} SOL)")

    result = await execute_buy(
        chat_id=chat_id,
        token_address=token_address,
        symbol=symbol,
        amount_sol=amount_sol,
        entry_price=entry_price,
        auto=True,
    )

    if result.get("success"):
        from core.advanced_trader import set_token_cooldown
        set_token_cooldown(token_address, chat_id)

    return result
