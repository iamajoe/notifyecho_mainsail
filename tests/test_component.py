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
        self.printing = False

    def is_ready(self) -> bool:
        return self.ready

    def is_printing(self) -> bool:
        return self.printing


class FakeUpdater:
    def __init__(self, status: Dict[str, Any] = None) -> None:
        self.status = status or {
            "name": "notifyecho",
            "version": "v0.1.0-0",
            "remote_version": "v0.1.1-0",
            "current_hash": "aaaa",
            "remote_hash": "bbbb",
            "commits_behind_count": 1,
            "is_valid": True,
            "channel": "stable",
            "warnings": [],
            "anomalies": [],
        }
        self.refreshed = False
        self.updated = False
        self.update_result = True
        self.update_error = None

    def get_update_status(self) -> Dict[str, Any]:
        return dict(self.status)

    async def refresh(self) -> None:
        self.refreshed = True
        self.status["current_hash"] = "bbbb"
        self.status["remote_hash"] = "bbbb"
        self.status["commits_behind_count"] = 0
        self.status["version"] = self.status["remote_version"]

    async def update(self) -> bool:
        if self.update_error is not None:
            raise self.update_error
        self.updated = True
        return self.update_result


class FakeUpdateManager:
    def __init__(self, updater: FakeUpdater = None) -> None:
        self.updaters = {"notifyecho": updater or FakeUpdater()}
        self.cmd_request_lock = asyncio.Lock()
        self.busy = False
        self.cmd_helper = types.SimpleNamespace(
            is_update_busy=lambda: self.busy
        )

    def get_updaters(self) -> Dict[str, FakeUpdater]:
        return self.updaters


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
        self.update_manager = None
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
            "update_manager": self.update_manager,
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
        self.assertIn("/server/notifyecho/update", paths)
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

    async def test_static_endpoints_return_assets(self) -> None:
        ui = await self.component._handle_ui(FakeWebRequest(RequestType.GET, {}))
        script = await self.component._handle_app_js(FakeWebRequest(RequestType.GET, {}))
        styles = await self.component._handle_style_css(
            FakeWebRequest(RequestType.GET, {})
        )

        self.assertIn("NotifyEcho", ui)
        self.assertIn("/settings", script)
        self.assertIn(".event-row", styles)

    async def test_update_status_reports_plugin_state(self) -> None:
        self.server.update_manager = FakeUpdateManager()

        result = await self.component._handle_update(
            FakeWebRequest(RequestType.GET, {})
        )

        self.assertTrue(result["available"])
        self.assertTrue(result["updatable"])
        self.assertTrue(result["tagged"])
        self.assertTrue(result["updateAllowed"])
        self.assertEqual(result["channel"], "stable")
        self.assertEqual(result["commitsBehind"], 1)

    async def test_update_status_without_update_manager(self) -> None:
        result = await self.component._handle_update(
            FakeWebRequest(RequestType.GET, {})
        )

        self.assertFalse(result["available"])
        self.assertIn("not enabled", result["message"])

    async def test_update_refresh_reports_new_state(self) -> None:
        updater = FakeUpdater()
        self.server.update_manager = FakeUpdateManager(updater)

        result = await self.component._handle_update(
            FakeWebRequest(RequestType.POST, {"action": "refresh"})
        )

        self.assertFalse(result["started"])
        self.assertTrue(updater.refreshed)
        self.assertFalse(result["status"]["updatable"])
        self.assertEqual(result["status"]["version"], "v0.1.1-0")

    async def test_update_starts_background_task(self) -> None:
        updater = FakeUpdater()
        self.server.update_manager = FakeUpdateManager(updater)

        result = await self.component._handle_update(
            FakeWebRequest(RequestType.POST, {"action": "update"})
        )

        self.assertTrue(result["started"])
        self.assertTrue(result["status"]["busy"])
        await _run_next_task(self.server)
        self.assertTrue(updater.updated)
        self.assertFalse(self.component._update_running)
        self.assertTrue(self.component._last_update["ok"])

    async def test_update_records_failure(self) -> None:
        updater = FakeUpdater()
        updater.update_error = RuntimeError("git failed")
        self.server.update_manager = FakeUpdateManager(updater)

        await self.component._handle_update(
            FakeWebRequest(RequestType.POST, {"action": "update"})
        )
        await _run_next_task(self.server)

        self.assertFalse(self.component._last_update["ok"])
        self.assertIn("git failed", self.component._last_update["message"])

    async def test_update_refused_while_printing(self) -> None:
        self.server.klippy.printing = True
        self.server.update_manager = FakeUpdateManager()

        with self.assertRaises(ServerError):
            await self.component._handle_update(
                FakeWebRequest(RequestType.POST, {"action": "update"})
            )

        self.assertEqual(self.server.eventloop.tasks, [])

    async def test_update_rejects_unknown_action(self) -> None:
        self.server.update_manager = FakeUpdateManager()

        with self.assertRaises(ServerError):
            await self.component._handle_update(
                FakeWebRequest(RequestType.POST, {"action": "nope"})
            )

    async def test_update_refused_when_not_on_tag(self) -> None:
        updater = FakeUpdater()
        updater.status["version"] = "v0.1.0-5"
        self.server.update_manager = FakeUpdateManager(updater)

        state = await self.component._handle_update(
            FakeWebRequest(RequestType.GET, {})
        )
        self.assertFalse(state["tagged"])
        self.assertFalse(state["updateAllowed"])
        self.assertFalse(state["updatable"])

        with self.assertRaises(ServerError):
            await self.component._handle_update(
                FakeWebRequest(RequestType.POST, {"action": "update"})
            )
        self.assertEqual(self.server.eventloop.tasks, [])

    async def test_update_refused_on_dev_channel(self) -> None:
        updater = FakeUpdater()
        updater.status["channel"] = "dev"
        self.server.update_manager = FakeUpdateManager(updater)

        state = await self.component._handle_update(
            FakeWebRequest(RequestType.GET, {})
        )
        self.assertTrue(state["tagged"])
        self.assertFalse(state["updateAllowed"])
        self.assertFalse(state["updatable"])

        with self.assertRaises(ServerError):
            await self.component._handle_update(
                FakeWebRequest(RequestType.POST, {"action": "update"})
            )
        self.assertEqual(self.server.eventloop.tasks, [])

    async def test_update_requires_update_manager(self) -> None:
        with self.assertRaises(ServerError):
            await self.component._handle_update(
                FakeWebRequest(RequestType.POST, {"action": "update"})
            )

    async def test_test_endpoint_rejects_unknown_event(self) -> None:
        with self.assertRaises(ServerError):
            await self.component._handle_test(
                FakeWebRequest(RequestType.POST, {"eventKey": "nope"})
            )

    async def test_test_endpoint_requires_token(self) -> None:
        self.component.settings = _configured_settings()
        self.component.settings["token"] = ""

        with self.assertRaises(ServerError):
            await self.component._handle_test(
                FakeWebRequest(
                    RequestType.POST,
                    {
                        "eventKey": "print_complete",
                        "workflowId": "11111111-1111-1111-1111-111111111111",
                    },
                )
            )

    async def test_verify_requires_token(self) -> None:
        self.component.settings = _configured_settings()
        self.component.settings["token"] = ""

        with self.assertRaises(ServerError):
            await self.component._handle_verify(
                FakeWebRequest(
                    RequestType.POST,
                    {"workflowId": "11111111-1111-1111-1111-111111111111"},
                )
            )

    async def test_ready_event_schedules_notification(self) -> None:
        self.component.settings = _configured_settings()

        await self.component._on_klippy_ready()
        await _run_next_task(self.server)

        self.assertEqual(
            self.server.http.last_post["body"]["kind"], "klipper.ready"
        )
        self.assertTrue(self.server.klippy_apis.subscribed)

    async def test_shutdown_event_schedules_notification(self) -> None:
        self.component.settings = _configured_settings()

        self.component._on_klippy_shutdown()
        await _run_next_task(self.server)

        self.assertEqual(
            self.server.http.last_post["body"]["kind"], "klipper.shutdown"
        )

    async def test_unexpected_disconnect_schedules_error(self) -> None:
        self.component.settings = _configured_settings()
        self.component._klippy_was_ready = True

        self.component._on_klippy_disconnect()
        await _run_next_task(self.server)

        body = self.server.http.last_post["body"]
        self.assertEqual(body["kind"], "klipper.error")
        self.assertEqual(body["metadata"]["errorSource"], "klippy_disconnect")

    async def test_disconnect_after_shutdown_does_not_schedule_error(self) -> None:
        self.component.settings = _configured_settings()
        self.component._klippy_was_ready = True
        self.component._shutdown_seen = True

        self.component._on_klippy_disconnect()

        self.assertEqual(self.server.eventloop.tasks, [])

    async def test_klippy_started_error_schedules_error(self) -> None:
        self.component.settings = _configured_settings()

        self.component._on_klippy_started(FakeState("error", "config error"))
        await _run_next_task(self.server)

        body = self.server.http.last_post["body"]
        self.assertEqual(body["kind"], "klipper.error")
        self.assertEqual(body["metadata"]["errorSource"], "klippy_startup")
        self.assertIn("config error", body["content"]["message"])

    async def test_plugin_error_is_throttled(self) -> None:
        self.component.settings = _configured_settings()

        self.component._report_plugin_error("first")
        self.component._report_plugin_error("second")

        self.assertEqual(len(self.server.eventloop.tasks), 1)

    async def test_print_started_resets_progress(self) -> None:
        self.component.settings = _configured_settings()
        self.component.progress.set_milestones([25])
        self.component.progress.update(0.5)

        self.component._on_job_state_changed(
            "started", {}, {"state": "printing", "filename": "part.gcode"}
        )
        await _run_next_task(self.server)

        self.assertEqual(self.component.progress.update(0.25), [25])

    async def test_progress_initial_sync_primes_milestones(self) -> None:
        self.component.settings = _configured_settings()
        self.component.progress.set_milestones([25, 50, 75])
        self.component._progress_synced = False
        self.server.job_state.stats = {"state": "printing", "filename": "part.gcode"}

        self.component._on_virtual_sdcard_update(
            {"virtual_sdcard": {"progress": 0.50}}, 0.0
        )
        self.assertEqual(self.server.eventloop.tasks, [])

        self.component._on_virtual_sdcard_update(
            {"virtual_sdcard": {"progress": 0.75}}, 0.0
        )
        self.assertEqual(len(self.server.eventloop.tasks), 1)

    async def test_dispatch_failure_reports_error_event(self) -> None:
        self.component.settings = _configured_settings()
        self.server.http.response = FakeResponse(500, b'{"error":{"message":"boom"}}')

        result = await self.component._dispatch_event(
            "print_complete",
            print_stats={"state": "complete", "filename": "part.gcode"},
        )
        self.assertFalse(result.ok)
        await _run_next_task(self.server)

        self.assertEqual(
            self.server.http.last_post["body"]["kind"], "klipper.error"
        )
        self.assertEqual(
            self.server.http.last_post["body"]["metadata"]["errorSource"], "plugin"
        )

    async def test_failed_error_event_does_not_recurse(self) -> None:
        self.component.settings = _configured_settings()
        self.server.http.response = FakeResponse(500, b"{}")

        result = await self.component._dispatch_event("error")

        self.assertFalse(result.ok)
        self.assertEqual(self.server.eventloop.tasks, [])


class FakeState:
    def __init__(self, name: str, message: str = "") -> None:
        self._name = name
        self.message = message

    def __str__(self) -> str:
        return self._name


async def _run_next_task(server: FakeServer) -> None:
    if not server.eventloop.tasks:
        raise AssertionError("Expected a scheduled task")
    await server.eventloop.tasks.pop(0)


def _configured_settings() -> Dict[str, Any]:
    from notifyecho.settings import default_settings, normalize_settings

    settings = default_settings()
    settings["token"] = "pk_test"
    settings["defaultWorkflowId"] = "11111111-1111-1111-1111-111111111111"
    return normalize_settings(settings)


if __name__ == "__main__":
    unittest.main()
