from __future__ import annotations

import datetime
import logging
import pathlib
import time
from typing import Any, Dict, Optional

from moonraker.common import RequestType

from .client import NotifyEchoClient, SendResult
from .payload import build_notify_request
from .progress import ProgressTracker
from .settings import (
    EVENT_DEFINITIONS_BY_KEY,
    KIND_BY_KEY,
    SettingsError,
    default_settings,
    event_catalog,
    is_event_enabled,
    normalize_base_url,
    normalize_settings,
    normalize_uuid,
    resolve_workflow_id,
)

DB_NAMESPACE = "notifyecho"
DB_KEY = "settings"
STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"
PLUGIN_ERROR_THROTTLE_SECONDS = 60.0

JOB_EVENT_KEYS = {
    "started": "print_started",
    "paused": "print_paused",
    "resumed": "print_resumed",
    "complete": "print_complete",
    "cancelled": "print_cancelled",
    "error": "print_failed",
}

LOGGER = logging.getLogger(__name__)


class NotifyEcho:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self.eventloop = self.server.get_event_loop()
        self.db = self.server.lookup_component("database")
        self.http = self.server.lookup_component("http_client")
        self.client = NotifyEchoClient(self.http)

        self.settings: Dict[str, Any] = default_settings()
        self.progress = ProgressTracker(self.settings["progressMilestones"])
        self._last_send: Optional[Dict[str, Any]] = None
        self._last_plugin_error_at = 0.0

        self._progress_subscribed = False
        self._progress_synced = False
        self._klippy_was_ready = False
        self._shutdown_seen = False

        self._register_endpoints()
        self._register_handlers()

    async def component_init(self) -> None:
        stored = await self.db.get_item(DB_NAMESPACE, DB_KEY, default_settings())
        try:
            self.settings = normalize_settings(stored)
        except SettingsError as exc:
            LOGGER.warning("NotifyEcho settings invalid, using defaults: %s", exc)
            self.settings = default_settings()
        self.progress.set_milestones(self.settings["progressMilestones"])

        klippy = self.server.lookup_component("klippy_connection", None)
        if klippy is not None and klippy.is_ready():
            self._klippy_was_ready = True
            await self._subscribe_progress()

    def _register_endpoints(self) -> None:
        self.server.register_endpoint(
            "/server/notifyecho/ui", RequestType.GET, self._handle_ui,
            wrap_result=False, content_type="text/html; charset=utf-8",
        )
        self.server.register_endpoint(
            "/server/notifyecho/static/app.js", RequestType.GET,
            self._handle_app_js, wrap_result=False,
            content_type="application/javascript; charset=utf-8",
        )
        self.server.register_endpoint(
            "/server/notifyecho/static/style.css", RequestType.GET,
            self._handle_style_css, wrap_result=False,
            content_type="text/css; charset=utf-8",
        )
        self.server.register_endpoint(
            "/server/notifyecho/settings",
            RequestType.GET | RequestType.POST,
            self._handle_settings,
        )
        self.server.register_endpoint(
            "/server/notifyecho/verify", RequestType.POST,
            self._handle_verify,
        )
        self.server.register_endpoint(
            "/server/notifyecho/test", RequestType.POST,
            self._handle_test,
        )

    def _register_handlers(self) -> None:
        self.server.register_event_handler(
            "job_state:state_changed", self._on_job_state_changed
        )
        self.server.register_event_handler(
            "server:klippy_ready", self._on_klippy_ready
        )
        self.server.register_event_handler(
            "server:klippy_started", self._on_klippy_started
        )
        self.server.register_event_handler(
            "server:klippy_shutdown", self._on_klippy_shutdown
        )
        self.server.register_event_handler(
            "server:klippy_disconnect", self._on_klippy_disconnect
        )

    # ------------------------------------------------------------------
    # HTTP endpoints

    async def _handle_ui(self, web_request: Any) -> str:
        return _read_static("index.html")

    async def _handle_app_js(self, web_request: Any) -> str:
        return _read_static("app.js")

    async def _handle_style_css(self, web_request: Any) -> str:
        return _read_static("style.css")

    async def _handle_settings(self, web_request: Any) -> Dict[str, Any]:
        if web_request.get_request_type() != RequestType.GET:
            raw = web_request.get("settings", None)
            if not isinstance(raw, dict):
                raise self.server.error("A settings object is required.", 400)
            try:
                settings = normalize_settings(raw)
            except SettingsError as exc:
                raise self.server.error(str(exc), 400)

            await self.db.insert_item(DB_NAMESPACE, DB_KEY, settings)
            self.settings = settings
            self.progress.set_milestones(settings["progressMilestones"])

        return {
            "settings": self.settings,
            "events": event_catalog(),
            "lastSend": self._last_send,
        }

    async def _handle_verify(self, web_request: Any) -> Dict[str, Any]:
        base_url = self._validated_base_url(
            web_request.get_str("baseUrl", self.settings["baseUrl"])
        )
        token = web_request.get_str("token", self.settings["token"]).strip()
        workflow_id = self._validated_workflow_id(
            web_request.get_str("workflowId", "")
        )
        if not token:
            raise self.server.error("A bearer token is required.", 400)
        if not workflow_id:
            raise self.server.error("A workflow ID is required.", 400)

        result = await self.client.verify(base_url, token, workflow_id)
        return {
            "valid": result.valid,
            "httpStatus": result.status_code,
            "name": result.name,
            "status": result.status,
            "message": result.message,
        }

    async def _handle_test(self, web_request: Any) -> Dict[str, Any]:
        event_key = web_request.get_str("eventKey")
        if event_key not in EVENT_DEFINITIONS_BY_KEY:
            raise self.server.error("Unknown event: %s" % event_key, 400)

        base_url = self._validated_base_url(
            web_request.get_str("baseUrl", self.settings["baseUrl"])
        )
        token = web_request.get_str("token", self.settings["token"]).strip()
        if not token:
            raise self.server.error("A bearer token is required.", 400)

        override = dict(self.settings)
        override["baseUrl"] = base_url
        override["token"] = token

        raw_workflow = web_request.get_str("workflowId", "")
        if raw_workflow.strip():
            workflow_id = self._validated_workflow_id(raw_workflow)
            override["defaultWorkflowId"] = workflow_id
        else:
            workflow_id = resolve_workflow_id(override, event_key)

        if not workflow_id:
            raise self.server.error("A workflow ID is required.", 400)

        stats, previous, extra = self._test_event_data(event_key)
        result = await self._dispatch_event(
            event_key,
            print_stats=stats,
            prev_stats=previous,
            extra=extra,
            override=override,
            force_workflow=workflow_id,
            ignore_enabled=True,
        )
        if result is None:
            return {
                "ok": False,
                "httpStatus": 0,
                "message": "The event was skipped because no workflow was resolved.",
            }
        return {
            "ok": result.ok,
            "httpStatus": result.status_code,
            "message": result.message,
        }

    # ------------------------------------------------------------------
    # Moonraker events

    def _on_job_state_changed(
        self,
        job_event: Any,
        prev_stats: Dict[str, Any],
        new_stats: Dict[str, Any],
    ) -> None:
        event_key = JOB_EVENT_KEYS.get(str(job_event).lower())
        if event_key is None:
            return

        if event_key == "print_started":
            self.progress.reset()
            self._progress_synced = True

        self.eventloop.create_task(
            self._dispatch_event(
                event_key, print_stats=new_stats, prev_stats=prev_stats
            )
        )

    async def _on_klippy_ready(self) -> None:
        self._klippy_was_ready = True
        self._shutdown_seen = False
        await self._subscribe_progress()
        self.eventloop.create_task(self._dispatch_event("ready"))

    def _on_klippy_started(self, state: Any) -> None:
        self._shutdown_seen = False
        if str(state).lower() != "error":
            return
        message = getattr(state, "message", "") or "Klipper started in an error state."
        self.eventloop.create_task(
            self._dispatch_event(
                "error",
                extra={"error": message, "errorSource": "klippy_startup"},
            )
        )

    def _on_klippy_shutdown(self) -> None:
        self._shutdown_seen = True
        self.eventloop.create_task(self._dispatch_event("shutdown"))

    def _on_klippy_disconnect(self) -> None:
        was_ready = self._klippy_was_ready
        was_shutdown = self._shutdown_seen
        self._klippy_was_ready = False
        self._progress_subscribed = False
        self._progress_synced = False

        if was_ready and not was_shutdown and self.server.is_running():
            self.eventloop.create_task(
                self._dispatch_event(
                    "error",
                    extra={
                        "error": "Klipper disconnected unexpectedly.",
                        "errorSource": "klippy_disconnect",
                    },
                )
            )

    def _on_virtual_sdcard_update(
        self, data: Dict[str, Any], eventtime: float
    ) -> None:
        if not isinstance(data, dict):
            return
        virtual_sdcard = data.get("virtual_sdcard")
        if not isinstance(virtual_sdcard, dict):
            return
        progress = virtual_sdcard.get("progress")
        if not isinstance(progress, (int, float)):
            return

        if not self._progress_synced:
            self.progress.prime(float(progress))
            self._progress_synced = True
            return

        stats = self._job_stats()
        if stats.get("state") != "printing":
            return

        for milestone in self.progress.update(float(progress)):
            self.eventloop.create_task(
                self._dispatch_event(
                    "print_progress",
                    print_stats=stats,
                    extra={"progress": float(progress), "milestone": milestone},
                )
            )

    async def _subscribe_progress(self) -> None:
        if self._progress_subscribed:
            return
        apis = self.server.lookup_component("klippy_apis", None)
        if apis is None:
            return
        try:
            result = await apis.subscribe_objects(
                {"virtual_sdcard": None}, self._on_virtual_sdcard_update
            )
        except Exception as exc:
            LOGGER.debug("NotifyEcho could not subscribe to virtual_sdcard: %s", exc)
            return

        self._progress_subscribed = True
        self._progress_synced = True
        if isinstance(result, dict):
            virtual_sdcard = result.get("virtual_sdcard")
            if isinstance(virtual_sdcard, dict):
                progress = virtual_sdcard.get("progress")
                if isinstance(progress, (int, float)):
                    self.progress.prime(float(progress))

    # ------------------------------------------------------------------
    # Sending

    async def _dispatch_event(
        self,
        event_key: str,
        print_stats: Optional[Dict[str, Any]] = None,
        prev_stats: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
        override: Optional[Dict[str, Any]] = None,
        force_workflow: Optional[str] = None,
        ignore_enabled: bool = False,
    ) -> Optional[SendResult]:
        settings = override or self.settings
        if not ignore_enabled and not is_event_enabled(settings, event_key):
            return None

        workflow_id = force_workflow or resolve_workflow_id(settings, event_key)
        token = str(settings.get("token", "")).strip()
        if not workflow_id or not token:
            LOGGER.debug(
                "NotifyEcho event %s skipped: workflow or token not configured",
                event_key,
            )
            return None

        kind = KIND_BY_KEY[event_key]
        payload = build_notify_request(
            event_key=event_key,
            kind=kind,
            print_stats=print_stats,
            prev_stats=prev_stats,
            printer_info=self._printer_info(),
            extra=extra,
        )
        result = await self.client.send(
            settings["baseUrl"], token, workflow_id, payload
        )

        self._last_send = {
            "at": _utc_now(),
            "eventKey": event_key,
            "kind": kind,
            "ok": result.ok,
            "httpStatus": result.status_code,
            "message": result.message,
        }

        if result.ok:
            LOGGER.debug("NotifyEcho event %s accepted (%s)", event_key, result.status_code)
        else:
            LOGGER.warning(
                "NotifyEcho event %s failed (%s): %s",
                event_key,
                result.status_code,
                result.message,
            )
            if event_key != "error":
                self._report_plugin_error(
                    "NotifyEcho send failed for %s: %s" % (kind, result.message)
                )

        return result

    def _report_plugin_error(self, message: str) -> None:
        now = time.time()
        if now - self._last_plugin_error_at < PLUGIN_ERROR_THROTTLE_SECONDS:
            return
        self._last_plugin_error_at = now
        self.eventloop.create_task(
            self._dispatch_event(
                "error",
                extra={"error": message, "errorSource": "plugin"},
            )
        )

    # ------------------------------------------------------------------
    # Helpers

    def _job_stats(self) -> Dict[str, Any]:
        job_state = self.server.lookup_component("job_state", None)
        if job_state is None:
            return {}
        try:
            return job_state.get_last_stats()
        except Exception:
            return {}

    def _printer_info(self) -> Dict[str, Any]:
        hostname, port = self.server.get_host_info()
        app_args = self.server.get_app_args()
        return {
            "hostname": hostname,
            "port": port,
            "moonrakerVersion": app_args.get("software_version") or "",
        }

    def _validated_base_url(self, raw: str) -> str:
        try:
            return normalize_base_url(raw)
        except SettingsError as exc:
            raise self.server.error(str(exc), 400)

    def _validated_workflow_id(self, raw: str) -> str:
        try:
            return normalize_uuid(raw, "Workflow ID")
        except SettingsError as exc:
            raise self.server.error(str(exc), 400)

    def _test_event_data(
        self, event_key: str
    ) -> tuple:
        if event_key in ("ready", "shutdown", "error"):
            extra = {}
            if event_key == "error":
                extra = {
                    "error": "Test system error from the NotifyEcho Mainsail plugin.",
                    "errorSource": "test",
                }
            return None, None, extra

        state = "printing"
        if event_key == "print_complete":
            state = "complete"
        elif event_key == "print_cancelled":
            state = "cancelled"
        elif event_key == "print_failed":
            state = "error"

        stats: Dict[str, Any] = {
            "state": state,
            "filename": "notifyecho-test.gcode",
            "print_duration": 3661.0,
            "total_duration": 3721.0,
            "filament_used": 1234.5,
            "info": {"current_layer": 50, "total_layer": 100},
        }
        previous = dict(stats)
        previous["state"] = "printing"

        extra = {}
        if event_key == "print_progress":
            extra = {"progress": 0.5, "milestone": 50}
        elif event_key == "print_failed":
            extra = {"error": "Test print failure.", "errorSource": "test"}
        return stats, previous, extra


def load_component(config: Any) -> NotifyEcho:
    return NotifyEcho(config)


def _read_static(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
