from __future__ import annotations

import asyncio
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "moonraker_component"))

from notifyecho.client import NotifyEchoClient  # noqa: E402


class FakeResponse:
    def __init__(self, code: int, body: bytes = b"", error: object = None) -> None:
        self.code = code
        self.body = body
        self.error = error


class FakeHttp:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_url = ""
        self.last_headers = {}
        self.last_body = None
        self.last_kwargs = {}

    async def request(self, method, url, headers=None, **kwargs):
        self.last_url = url
        self.last_headers = headers or {}
        self.last_kwargs = kwargs
        return self.response

    async def post(self, url, body=None, headers=None, **kwargs):
        self.last_url = url
        self.last_headers = headers or {}
        self.last_body = body
        self.last_kwargs = kwargs
        return self.response


class VerifyTest(unittest.TestCase):
    def test_valid_workflow(self) -> None:
        http = FakeHttp(
            FakeResponse(200, b'{"name":"Print complete","status":"ok"}')
        )
        client = NotifyEchoClient(http)

        result = asyncio.run(
            client.verify(
                "https://notifyecho.com",
                "pk_live_abc",
                "11111111-1111-1111-1111-111111111111",
            )
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.name, "Print complete")
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            http.last_url,
            "https://notifyecho.com/api/notify/11111111-1111-1111-1111-111111111111/status",
        )
        self.assertEqual(http.last_headers["Authorization"], "Bearer pk_live_abc")
        self.assertFalse(http.last_kwargs["enable_cache"])

    def test_invalid_token(self) -> None:
        http = FakeHttp(FakeResponse(401, b'{"error":{"code":"invalid_api_key"}}'))
        client = NotifyEchoClient(http)

        result = asyncio.run(client.verify("https://example.test", "bad", "wf"))

        self.assertFalse(result.valid)
        self.assertEqual(result.status_code, 401)
        self.assertIn("Invalid bearer token", result.message)

    def test_missing_workflow(self) -> None:
        http = FakeHttp(FakeResponse(404, b"{}"))
        client = NotifyEchoClient(http)

        result = asyncio.run(client.verify("https://example.test", "token", "wf"))

        self.assertFalse(result.valid)
        self.assertIn("not found", result.message)

    def test_network_failure(self) -> None:
        class BrokenHttp:
            async def request(self, *args, **kwargs):
                raise OSError("no route to host")

        client = NotifyEchoClient(BrokenHttp())

        result = asyncio.run(client.verify("https://example.test", "token", "wf"))

        self.assertFalse(result.valid)
        self.assertIn("no route", result.message)


class SendTest(unittest.TestCase):
    def test_accepted(self) -> None:
        http = FakeHttp(FakeResponse(202, b'{"status":"accepted"}'))
        client = NotifyEchoClient(http)

        result = asyncio.run(
            client.send(
                "https://notifyecho.com",
                "pk_live_abc",
                "11111111-1111-1111-1111-111111111111",
                {"kind": "klipper.ready", "content": {"title": "Ready"}},
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 202)
        self.assertEqual(
            http.last_url,
            "https://notifyecho.com/api/notify/11111111-1111-1111-1111-111111111111",
        )
        self.assertEqual(http.last_headers["Authorization"], "Bearer pk_live_abc")
        self.assertIn("Idempotency-Key", http.last_headers)
        self.assertEqual(http.last_body["kind"], "klipper.ready")

    def test_rejected(self) -> None:
        http = FakeHttp(
            FakeResponse(400, b'{"error":{"code":"invalid_content","message":"bad content"}}')
        )
        client = NotifyEchoClient(http)

        result = asyncio.run(
            client.send("https://example.test", "token", "wf", {"kind": "test"})
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.message, "bad content")

    def test_network_failure(self) -> None:
        class BrokenHttp:
            async def post(self, *args, **kwargs):
                raise OSError("connection refused")

        client = NotifyEchoClient(BrokenHttp())

        result = asyncio.run(
            client.send("https://example.test", "token", "wf", {"kind": "test"})
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 0)
        self.assertIn("connection refused", result.message)


if __name__ == "__main__":
    unittest.main()
