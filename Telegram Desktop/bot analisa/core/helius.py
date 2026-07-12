import json
from typing import Dict, List, Optional

PUBLIC_RPC = "https://api.mainnet-beta.solana.com"


class HeliusClient:
    TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

    def __init__(self, api_key: str = ""):
        if api_key:
            self._rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        else:
            self._rpc_url = PUBLIC_RPC
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _call(self, method: str, params: list) -> dict:
        import aiohttp

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return {}
                return await resp.json()

    async def close(self):
        pass

    async def get_balance(self, wallet_address: str) -> Optional[float]:
        result = await self._call("getBalance", [wallet_address])
        try:
            lamports = result.get("result", {}).get("value", 0)
            return float(lamports) / 1e9
        except Exception:
            return None

    async def get_signatures(self, address: str, limit: int = 20, before: str = None) -> List[Dict]:
        params = [address, {"limit": limit}]
        if before:
            params[1]["before"] = before
        result = await self._call("getSignaturesForAddress", params)
        try:
            return result.get("result", [])
        except Exception:
            return []

    async def get_transaction(self, signature: str) -> Optional[Dict]:
        result = await self._call("getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        try:
            return result.get("result")
        except Exception:
            return None

    async def get_token_accounts(self, wallet_address: str, program_id: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA") -> List[Dict]:
        result = await self._call("getTokenAccountsByOwner", [
            wallet_address,
            {"programId": program_id},
            {"encoding": "jsonParsed"}
        ])
        try:
            return result.get("result", {}).get("value", [])
        except Exception:
            return []

    async def get_token_balance(self, wallet_address: str, token_mint: str) -> Optional[Dict]:
        result = await self._call("getTokenAccountsByOwner", [
            wallet_address,
            {"mint": token_mint},
            {"encoding": "jsonParsed"}
        ])
        try:
            accounts = result.get("result", {}).get("value", [])
            if accounts:
                info = accounts[0].get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                return {
                    "amount": info.get("tokenAmount", {}).get("amount", "0"),
                    "ui_amount": info.get("tokenAmount", {}).get("uiAmount", 0),
                    "decimals": info.get("tokenAmount", {}).get("decimals", 0),
                }
        except Exception:
            pass
        return None

    async def get_mint_info(self, token_address: str) -> Optional[Dict]:
        result = await self._call("getAccountInfo", [
            token_address,
            {"encoding": "jsonParsed"}
        ])

        try:
            value = result.get("result", {}).get("value")
            if not value:
                return None

            data = value.get("data", {})
            parsed = data.get("parsed", {})
            info = parsed.get("info", {})

            if not info:
                return None

            return {
                "mint_authority": info.get("mintAuthority"),
                "freeze_authority": info.get("freezeAuthority"),
                "decimals": info.get("decimals", 0),
                "supply": info.get("supply", "0"),
                "is_initialized": info.get("isInitialized", False),
            }
        except Exception:
            return None

    async def get_token_largest_holders(self, token_address: str, limit: int = 20) -> List[Dict]:
        result = await self._call("getTokenLargestAccounts", [token_address])

        try:
            accounts = result.get("result", {}).get("value", [])
            holders = []
            for acc in accounts[:limit]:
                holders.append({
                    "address": acc.get("address", ""),
                    "amount": float(acc.get("amount", "0")),
                    "ui_amount": acc.get("uiAmount", 0) or 0,
                    "decimals": acc.get("decimals", 0),
                })
            return holders
        except Exception:
            return []

    async def get_token_supply(self, token_address: str) -> Optional[Dict]:
        result = await self._call("getTokenSupply", [token_address])

        try:
            value = result.get("result", {}).get("value", {})
            if not value:
                return None
            return {
                "amount": value.get("amount", "0"),
                "decimals": value.get("decimals", 0),
                "ui_amount": value.get("uiAmount", 0),
            }
        except Exception:
            return None
