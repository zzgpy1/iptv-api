import asyncio
import socket
import unittest

from aiohttp import ClientSession, TCPConnector

from utils.speed import create_speed_test_session, _install_aiohttp_dns_error_filter


class FailingResolver:
    async def resolve(self, host, port=0, family=socket.AF_INET):
        await asyncio.sleep(0.02)
        raise socket.gaierror(-3, "Try again")

    async def close(self):
        pass


class SpeedDnsErrorLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_speed_session_installs_dns_error_filter(self):
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(None)

        async with create_speed_test_session(1):
            handler = loop.get_exception_handler()

        self.assertTrue(
            getattr(handler, "_filters_aiohttp_dns_shield_errors", False)
        )

    async def test_cancelled_aiohttp_dns_failure_is_filtered(self):
        loop = asyncio.get_running_loop()
        contexts = []
        loop.set_exception_handler(lambda _loop, context: contexts.append(context))
        _install_aiohttp_dns_error_filter()

        async with ClientSession(
            connector=TCPConnector(resolver=FailingResolver())
        ) as session:
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(
                    session.get("http://unresolvable.invalid"),
                    timeout=0.001,
                )
            await asyncio.sleep(0.05)

        self.assertEqual(contexts, [])

    async def test_unrelated_asyncio_exception_uses_previous_handler(self):
        loop = asyncio.get_running_loop()
        contexts = []
        loop.set_exception_handler(lambda _loop, context: contexts.append(context))
        _install_aiohttp_dns_error_filter()
        context = {
            "message": "unexpected background failure",
            "exception": RuntimeError("boom"),
        }

        loop.call_exception_handler(context)

        self.assertEqual(contexts, [context])
