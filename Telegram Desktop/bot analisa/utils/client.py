import aiohttp
import asyncio
import time
from typing import Optional, Dict, Any


class RateLimiter:
    def __init__(self, calls_per_second: float = 2.0):
        self.rate = calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            wait_time = max(0, (1.0 / self.rate) - (now - self.last_call))
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_call = time.monotonic()


class HttpClient:
    _instance: Optional["HttpClient"] = None

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._ratelimiters: Dict[str, RateLimiter] = {}

    @classmethod
    async def get_instance(cls) -> "HttpClient":
        if cls._instance is None:
            cls._instance = HttpClient()
            cls._instance._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )
        return cls._instance

    def _get_limiter(self, host: str) -> RateLimiter:
        if host not in self._ratelimiters:
            self._ratelimiters[host] = RateLimiter(calls_per_second=2.0)
        return self._ratelimiters[host]

    async def get(self, url: str, params: dict = None) -> Dict[str, Any]:
        client = await self.get_instance()
        host = url.split("/")[2]
        await self._get_limiter(host).wait()

        async with client._session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status} from {url}")
            return await resp.json()

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
            HttpClient._instance = None
