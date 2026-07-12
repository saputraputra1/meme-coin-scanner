import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TELEGRAM_PROXY
from httpx import AsyncClient, Proxy, Timeout


def create_bot(token: str):
    from telegram import Bot

    if TELEGRAM_PROXY:
        try:
            proxy_url = str(TELEGRAM_PROXY)
            transport_kwargs = {}

            if proxy_url.startswith("socks5://"):
                try:
                    import httpx_socks
                    transport = httpx_socks.AsyncProxyTransport.from_url(proxy_url)
                    transport_kwargs["transport"] = transport
                except ImportError:
                    proxy = Proxy(url=proxy_url)
                    transport_kwargs["proxy"] = proxy
            else:
                proxy = Proxy(url=proxy_url)
                transport_kwargs["proxy"] = proxy

            client = AsyncClient(
                timeout=Timeout(30.0),
                **transport_kwargs,
            )

            bot = Bot(token=token)
            bot._request._client = client
            return bot
        except Exception:
            pass

    return Bot(token=token)
