from __future__ import annotations

import asyncio
import enum
import pathlib
import sys
import types
import unittest
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "moonraker_component"))

# The component imports RequestType from Moonraker. Stub the tiny surface the
# component needs so these tests run without a Moonraker installation.
if "moonraker" not in sys.modules:
    moonraker_module = types.ModuleType("moonraker")
    common_module = types.ModuleType("moonraker.common")

    class RequestType(enum.Flag):
        GET = enum.auto()
        POST = enum.auto()
        DELETE = enum.auto()

    common_module.RequestType = RequestType
    moonraker_module.common = common_module
    sys.modules["moonraker"] = moonraker_module
    sys.modules["moonraker.common"] = common_module

from notifyecho.component import NotifyEcho  # noqa: E402

_MISSING = object()


class ServerError(Exception):
    pass


class FakeResponse:
    def __init__(self, code: int, body: bytes = b"", error: Any = None) -> None:
        self.code = code
        self.body = body
        self.error = error


class FakeEventLoop:
    def __init__(self) -> None:
        self.tasks: List[Any] = []

    def create_task(self, coro: Any) -> None:
        self.tasks.append(coro)

    def close_tasks(self) -> None:
        while self.tasks:
            coro = self.tasks.pop()
            coro.close()


class FakeDatabase:
    def __init__(self, stored: Any = None) -> None:
        self.stored = stored
        self.saved: Any = None

    async def get_item(self, namespace: str, key: str, default: Any = None) -> Any:
        return default if self.stored is None else self.stored

    async def insert_item(self, namespace: str, key: str, value: Any) -> None:
        self.saved = value
        self.stored = value


class FakeHttp:
    def __init__(self) -> None:
        self.response = FakeResponse(202, b'{"status":"accepted"}')
        self.last_post: Dict[str, Any] = {}
        self.last_request: Dict[str, Any] = {}

    async def post(self, url: str, body: Any = None, headers: Any = None, **kwargs: Any) -> FakeResponse:
        self.last_post = {"url": url, "body": body, "headers": headers, "kwargs": kwargs}
        return self.response

    async def request(self, method: str, url: str, headers: Any = None, **kwargs: Any) -> FakeResponse:
        self.last_request = {"method": method, "url": url, "headers": headers, "kwargs": kwargs}
        return self.response


class FakeKlippy:
    def __init__(self, ready: bool = False) -> None:
        self.ready = ready

    def is_ready(self) -> bool:
        return self.ready


class FakeJobState:
    def __init__(self) -> None:
        self.stats: Dict[str, Any] = {}

    def get_last_stats(self) -> Dict[str, Any]:
        return dict(self.stats)


class FakeKlippyApis:
    def __init__(self) -> None:
        self.subscribed = False

    async def subscribe_objects(self, objects: Any, callback: Any) -> Dict[str, Any]:
        self.subscribed = True
        return {"virtual_sdcard": {"progress": 0.0}}


class FakeServer:
    error = ServerError

    def __init__(self) -> None:
        self.eventloop = FakeEventLoop()
        self.db = FakeDatabase()
        self.http = FakeHttp()
        self.klippy = FakeKlippy()
        self.job_state = FakeJobState()
        self.klippy_apis = FakeKlippyApis()
        self.endpoints: List[Any] = []
        self.handlers: Dict[str, Any] = {}

    def get_event_loop(self) -> FakeEventLoop:
        return self.eventloop

    def lookup_component(self, name: str, default: Any = _MISSING) -> Any:
        components = {
            "database": self.db,
            "http_client": self.http,
            "klippy_connection": self.klippy,
            "job_state": self.job_state,
            "klippy_apis": self.klippy_apis,
        }
        if name in components:
            return components[name]
        if default is _MISSING:
            raise KeyError(name)
        return default

    def register_endpoint(self, path: str, methods: Any, callback: Any, **kwargs: Any) -> None:
        self.endpoints.append((path, methods, callback, kwargs))

    def register_event_handler(self, event: str, callback: Any) -> None:
        self.handlers[event] = callback

    def get_host_info(self) -> tuple:
        return ("voron", 7125)

    def get_app_args(self) -> Dict[str, Any]:
        return {"software_version": "v0.0.0-test"}

    def is_running(self) -> bool:
        return True


class FakeConfig:
    def __init__(self, server: FakeServer) -> None:
        self.server = server

    def get_server(self) -> FakeServer:
        return self.server


class FakeWebRequest:
    def __init__(self, method: Any, args: Dict[str, Any]) -> None:
        self.method = method
        self.args = args

    def get_request_type(self) -> Any:
        return self.method

    def get(self, key: str, default: Any = _MISSING) -> Any:
        if key in self.args:
            return self.args[key]
        if default is _MISSING:
            raise KeyError(key)
        return default

    def get_str(self, key: str, default: Any = _MISSING) -> str:
        value = self.get(key, default)
        return "" if value is None else str(value)


class ComponentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.server = FakeServer()
        self.component = NotifyEcho(FakeConfig(self.server))

    def tearDown(self) -> None:
        self.server.eventloop.close_tasks()

    async def test_component_init_loads_defaults_and_subscribes(self) -> None:
        self.server.klippy.ready = True

        await self.component.component_init()

        self.assertEqual(self.component.settings["baseUrl"], "https://notifyecho.com")
        self.assertTrue(self.server.klippy_apis.subscribed)

    async def test_endpoints_are_unique(self) -> None:
        paths = [endpoint[0] for endpoint in self.server.endpoints]

        self.assertEqual(len(paths), len(set(paths)))
        self.assertIn("/server/notifyecho/settings", paths)
        self.assertIn("/server/notifyecho/ui", paths)

    async def test_get_settings(self) -> None:
        result = await self.component._handle_settings(
            FakeWebRequest(RequestType.GET, {})
        )

        self.assertIn("settings", result)
        self.assertEqual(len(result["events"]), 10)
        self.assertIn("lastSend", result)

    async def test_save_settings_normalizes_and_persists(self) -> None:
        payload = {
            "baseUrl": "https://example.test/",
            "token": "pk_test",
            "defaultWorkflowId": "11111111-1111-1111-1111-111111111111",
            "advancedMode": True,
            "progressMilestones": "10, 50",
            "events": {"print_complete": {"enabled": False}},
        }

        result = await self.component._handle_settings(
            FakeWebRequest(RequestType.POST, {"settings": payload})
        )

        self.assertEqual(result["settings"]["baseUrl"], "https://example.test")
        self.assertEqual(result["settings"]["progressMilestones"], [10, 50])
        self.assertFalse(result["settings"]["events"]["print_complete"]["enabled"])
        self.assertIsNotNone(self.server.db.saved)

    async def test_save_settings_rejects_invalid(self) -> None:
        with self.assertRaises(ServerError):
            await self.component._handle_settings(
                FakeWebRequest(
                    RequestType.POST,
                    {"settings": {"baseUrl": "not-a-url"}},
                )
            )

    async def test_verify_workflow(self) -> None:
        self.server.http.response = FakeResponse(
            200, b'{"name":"Print complete","status":"ok"}'
        )

        result = await self.component._handle_verify(
            FakeWebRequest(
                RequestType.POST,
                {
                    "baseUrl": "https://notifyecho.com",
                    "token": "pk_test",
                    "workflowId": "11111111-1111-1111-1111-111111111111",
                },
            )
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["name"], "Print complete")
        self.assertEqual(
            self.server.http.last_request["url"],
            "https://notifyecho.com/api/notify/11111111-1111-1111-1111-111111111111/status",
        )

    async def test_verify_requires_uuid(self) -> None:
        with self.assertRaises(ServerError):
            await self.component._handle_verify(
                FakeWebRequest(
                    RequestType.POST,
                    {"token": "pk_test", "workflowId": "not-a-uuid"},
                )
            )

    async def test_dispatch_sends_enabled_event(self) -> None:
        self.component.settings = _configured_settings()

        result = await self.component._dispatch_event(
            "print_complete",
            print_stats={"state": "complete", "filename": "part.gcode"},
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(
            self.server.http.last_post["body"]["kind"],
            "klipper.job_state.complete",
        )
        self.assertIsNotNone(self.component._last_send)

    async def test_dispatch_skips_disabled_event(self) -> None:
        self.component.settings = _configured_settings()
        self.component.settings["events"]["print_complete"]["enabled"] = False

        result = await self.component._dispatch_event("print_complete")

        self.assertIsNone(result)
        self.assertEqual(self.server.http.last_post, {})

    async def test_dispatch_skips_missing_workflow(self) -> None:
        self.component.settings = _configured_settings()
        self.component.settings["defaultWorkflowId"] = ""

        result = await self.component._dispatch_event("print_complete")

        self.assertIsNone(result)
        self.assertEqual(self.server.http.last_post, {})

    async def test_print_progress_crosses_milestones(self) -> None:
        self.component.settings = _configured_settings()
        self.component.progress.set_milestones([25, 50])
        self.component._progress_synced = True
        self.server.job_state.stats = {"state": "printing", "filename": "part.gcode"}

        self.component._on_virtual_sdcard_update(
            {"virtual_sdcard": {"progress": 0.25}}, 0.0
        )
        self.component._on_virtual_sdcard_update(
            {"virtual_sdcard": {"progress": 0.25}}, 0.0
        )

        self.assertEqual(len(self.server.eventloop.tasks), 1)
        coro = self.server.eventloop.tasks.pop()
        await coro
        self.assertEqual(
            self.server.http.last_post["body"]["content"]["data"]["milestone"],
            25,
        )

    async def test_test_endpoint_sends_synthetic_event(self) -> None:
        self.component.settings = _configured_settings()

        result = await self.component._handle_test(
            FakeWebRequest(
                RequestType.POST,
                {
                    "eventKey": "print_complete",
                    "workflowId": "11111111-1111-1111-1111-111111111111",
                },
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            self.server.http.last_post["body"]["content"]["data"]["filename"],
            "notifyecho-test.gcode",
        )


def _configured_settings() -> Dict[str, Any]:
    from notifyecho.settings import default_settings, normalize_settings

    settings = default_settings()
    settings["token"] = "pk_test"
    settings["defaultWorkflowId"] = "11111111-1111-1111-1111-111111111111"
    return normalize_settings(settings)


if __name__ == "__main__":
    unittest.main()
