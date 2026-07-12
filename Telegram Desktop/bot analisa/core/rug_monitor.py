import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List
from config import HELIUS_API_KEY

logger = logging.getLogger("memecoin-bot")


async def check_rug_indicators(token_address: str, entry_price: float, entry_lp: float) -> Dict:
    from core.helius import HeliusClient
    from core.dexscreener import get_token_info

    result = {
        "is_rug": False,
        "triggers": [],
        "price_change_pct": 0,
        "lp_change_pct": 0,
    }

    try:
        info = await get_token_info(token_address)
        if info:
            current_price = info.get("price_usd", 0)
            current_lp = info.get("liquidity_usd", 0)

            if entry_price > 0:
                price_change = ((current_price - entry_price) / entry_price) * 100
                result["price_change_pct"] = round(price_change, 2)

                if price_change < -50:
                    result["is_rug"] = True
                    result["triggers"].append(f"Price dropped {price_change:.0f}%")

            if entry_lp > 0:
                lp_change = ((current_lp - entry_lp) / entry_lp) * 100
                result["lp_change_pct"] = round(lp_change, 2)

                if lp_change < -50:
                    result["is_rug"] = True
                    result["triggers"].append(f"LP removed {lp_change:.0f}%")
    except Exception as e:
        logger.error(f"Rug check error: {e}")

    try:
        from core.helius import HeliusClient
        client = HeliusClient(HELIUS_API_KEY)
        sigs = await client.get_signatures(token_address, limit=5)
        if sigs:
            latest_sig = sigs[0]
            block_time = latest_sig.get("blockTime", 0)
            if block_time:
                now = datetime.now(timezone.utc).timestamp()
                age_seconds = now - block_time
                if age_seconds < 120:
                    tx = await client.get_transaction(latest_sig.get("signature", ""))
                    if tx:
                        meta = tx.get("meta", {})
                        post_balances = meta.get("postTokenBalances", [])
                        pre_balances = meta.get("preTokenBalances", [])

                        for post in post_balances:
                            owner = post.get("owner", "")
                            post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                            pre_amount = 0
                            for pre in pre_balances:
                                if pre.get("owner") == owner and pre.get("mint") == post.get("mint"):
                                    pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                                    break

                            if pre_amount > 0 and post_amount < pre_amount * 0.5:
                                sell_pct = ((pre_amount - post_amount) / pre_amount) * 100
                                if sell_pct > 30:
                                    result["is_rug"] = True
                                    result["triggers"].append(f"Large sell: {owner[:8]}... sold {sell_pct:.0f}%")

        await client.close()
    except Exception as e:
        logger.error(f"Rug on-chain check error: {e}")

    return result


async def monitor_positions():
    from core.position_tracker import update_position_price, close_position, get_open_positions, load_positions, save_positions
    from core.jupiter_trader import sell_token_by_sol_value
    from core.wallet_manager import get_wallet, get_decrypted_key
    from core.dexscreener import get_token_info
    from core.advanced_trader import load_trade_config, get_trailing_stop
    from config import AUTO_TRADE_ENABLED

    if not AUTO_TRADE_ENABLED:
        return

    positions = get_open_positions()
    if not positions:
        return

    all_positions = load_positions()
    need_save = False

    for pos in positions:
        try:
            token_address = pos["token_address"]
            chat_id = pos["chat_id"]
            entry_price = pos["entry_price"]

            wallet = get_wallet(chat_id)
            if not wallet or not wallet.get("auto_trade_enabled"):
                continue

            config = load_trade_config(chat_id)
            info = await get_token_info(token_address)
            if not info:
                continue

            current_price = info.get("price_usd", 0)
            updated = update_position_price(token_address, current_price)
            private_key = get_decrypted_key(chat_id)

            for updated_pos in updated:
                pnl_pct = updated_pos["pnl_pct"]
                stop_loss = wallet.get("stop_loss_pct", -40)
                take_profit = wallet.get("take_profit_pct", 100)
                slippage = wallet.get("slippage_bps", 500)
                partial_sold = updated_pos.get("partial_sold", 0)
                highest_price = updated_pos.get("highest_price", entry_price)

                rug = await check_rug_indicators(token_address, entry_price, info.get("liquidity_usd", 0))

                if rug["is_rug"]:
                    logger.info(f"RUG: {pos['symbol']}")
                    if private_key:
                        sell_result = await sell_token_by_sol_value(token_address, 1.0, slippage, private_key)
                        if sell_result.get("success"):
                            close_position(pos["id"], current_price, sell_result.get("tx_hash", ""), "rug_detected")
                    continue

                trail_stop_price = None
                if config.get("trailing_stop_enabled"):
                    trail_stop_price = get_trailing_stop(
                        entry_price, highest_price,
                        config.get("trailing_stop_start", 50),
                        config.get("trailing_stop_distance", 20),
                    )

                if trail_stop_price and current_price < trail_stop_price:
                    logger.info(f"TRAILING STOP: {pos['symbol']} at {pnl_pct:.0f}%")
                    if private_key:
                        sell_result = await sell_token_by_sol_value(token_address, 1.0, slippage, private_key)
                        if sell_result.get("success"):
                            close_position(pos["id"], current_price, sell_result.get("tx_hash", ""), "trailing_stop")
                    continue

                if pnl_pct <= stop_loss:
                    logger.info(f"STOP LOSS: {pos['symbol']} at {pnl_pct:.0f}%")
                    if private_key:
                        sell_result = await sell_token_by_sol_value(token_address, 1.0, slippage, private_key)
                        if sell_result.get("success"):
                            close_position(pos["id"], current_price, sell_result.get("tx_hash", ""), "stop_loss")
                    continue

                if config.get("partial_sell_enabled") and partial_sold < 1.0:
                    levels = config.get("partial_sell_levels", [])
                    for level in levels:
                        lvl_pct = level["pct"]
                        sell_portion = level["sell_portion"]
                        level_key = str(lvl_pct)
                        already_sold_at_level = level_key in updated_pos.get("partial_sold_levels", [])

                        if pnl_pct >= lvl_pct and not already_sold_at_level and partial_sold + sell_portion <= 1.0:
                            logger.info(f"PARTIAL SELL: {pos['symbol']} {int(sell_portion*100)}% at +{lvl_pct}%")
                            if private_key:
                                sell_result = await sell_token_by_sol_value(token_address, sell_portion, slippage, private_key)
                                if sell_result.get("success"):
                                    for p in all_positions:
                                        if p["id"] == pos["id"]:
                                            p["partial_sold"] = p.get("partial_sold", 0) + sell_portion
                                            levels_list = p.get("partial_sold_levels", [])
                                            levels_list.append(level_key)
                                            p["partial_sold_levels"] = levels_list
                                            p["updated_at"] = datetime.now(timezone.utc).isoformat()
                                            need_save = True
                                            break
                            break

                if pnl_pct >= take_profit and partial_sold == 0:
                    logger.info(f"TAKE PROFIT: {pos['symbol']} at {pnl_pct:.0f}%")
                    if private_key:
                        sell_result = await sell_token_by_sol_value(token_address, 0.5, slippage, private_key)
                        if sell_result.get("success"):
                            close_position(pos["id"], current_price, sell_result.get("tx_hash", ""), "take_profit_50%")

        except Exception as e:
            logger.error(f"Position monitor error: {e}")

    if need_save:
        save_positions(all_positions)


async def position_monitor_loop():
    logger.info("Position monitor started")
    while True:
        try:
            await monitor_positions()
        except Exception as e:
            logger.error(f"Position monitor loop error: {e}")
        await asyncio.sleep(180)
