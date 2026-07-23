import asyncio
import ssl

import certifi
from aiohttp import ClientSession, ClientTimeout

from utils.config import config
from utils.i18n import t
from utils.requests.tools import headers as default_headers
from utils.retry import max_retries


SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.load_verify_locations(cafile=certifi.where())


def merge_headers(headers_override=None):
    result = default_headers.copy()
    if headers_override:
        result.update({key: value for key, value in headers_override.items() if value is not None})
    return result


async def fetch_first(
        session: ClientSession,
        candidates: list[str],
        name: str,
        headers=None,
        timeout: int | float | None = None,
        as_bytes: bool = False,
        raise_for_status: bool = True,
        require_content: bool = False,
):
    last_error = None
    request_timeout = ClientTimeout(total=timeout or config.request_timeout)
    for attempt in range(max_retries):
        await asyncio.sleep(1)
        for url in candidates:
            try:
                async with session.get(
                        url,
                        headers=headers,
                        proxy=config.http_proxy or None,
                        ssl=SSL_CONTEXT,
                        timeout=request_timeout,
                ) as response:
                    if raise_for_status:
                        response.raise_for_status()
                    if as_bytes:
                        content = await response.read()
                    else:
                        content = await response.text(encoding="utf-8", errors="replace")
                    if require_content and not content:
                        raise ValueError("Empty response")
                    return content
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
        if name and attempt < max_retries - 1:
            print(t("msg.failed_retrying_count").format(name=name, count=attempt + 1), flush=True)
    if last_error:
        raise Exception(t("msg.failed_retry_max").format(name=name)) from last_error
    return b"" if as_bytes else ""


async def check_ipv6_support_async():
    url = "https://ipv6.tokyo.test-ipv6.com/ip/?callback=?&testdomain=test-ipv6.com&testname=test_aaaa"
    print(t("msg.check_ipv6_support"))
    try:
        async with ClientSession(trust_env=True) as session:
            async with session.get(
                    url,
                    proxy=config.http_proxy or None,
                    ssl=SSL_CONTEXT,
                    timeout=ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    print(t("msg.ipv6_supported"))
                    return True
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    print(t("msg.ipv6_not_supported"))
    return False
