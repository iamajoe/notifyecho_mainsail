#!/usr/bin/env python3
"""Local, dependency-free preview server for the NotifyEcho settings page.

It serves the real static assets and mocks the Moonraker endpoints the page
uses, so the UI can be developed without Klipper, Moonraker, or Mainsail.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "moonraker_component" / "notifyecho" / "static"
sys.path.insert(0, str(ROOT / "moonraker_component"))

from notifyecho.settings import (  # noqa: E402
    EVENT_DEFINITIONS_BY_KEY,
    SettingsError,
    default_settings,
    event_catalog,
    normalize_settings,
)

API_PREFIX = "/server/notifyecho"
STATIC_PREFIX = API_PREFIX + "/static/"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class DevState:
    def __init__(self) -> None:
        self.settings = default_settings()
        self.last_send: Any = None

    def update_state(self) -> dict:
        return {
            "available": True,
            "name": "notifyecho",
            "version": "v0.0.0",
            "remoteVersion": "v0.0.0",
            "fullVersion": "v0.0.0-0-gdev",
            "branch": "main",
            "channel": "stable",
            "tagged": True,
            "updateAllowed": True,
            "commitsBehind": 0,
            "updatable": False,
            "valid": True,
            "busy": False,
            "warnings": [],
            "anomalies": [],
            "lastUpdate": None,
        }


STATE = DevState()


class DevHandler(BaseHTTPRequestHandler):
    server_version = "NotifyEchoDev/1.0"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", API_PREFIX, API_PREFIX + "/", API_PREFIX + "/ui"):
            self._serve_static("index.html")
            return
        if path.startswith(STATIC_PREFIX):
            self._serve_static(unquote(path[len(STATIC_PREFIX):]))
            return
        if path == API_PREFIX + "/settings":
            self._json({"result": self._settings_payload()})
            return
        if path == API_PREFIX + "/update":
            self._json({"result": STATE.update_state()})
            return
        self._error(404, "Not found.")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        body = self._read_json()
        if body is None:
            return
        if not isinstance(body, dict):
            self._error(400, "Request body must be a JSON object.")
            return

        if path == API_PREFIX + "/settings":
            self._save_settings(body)
        elif path == API_PREFIX + "/verify":
            self._verify(body)
        elif path == API_PREFIX + "/test":
            self._test(body)
        elif path == API_PREFIX + "/update":
            self._update(body)
        else:
            self._error(404, "Not found.")

    def _settings_payload(self) -> dict:
        return {
            "settings": STATE.settings,
            "events": event_catalog(),
            "lastSend": STATE.last_send,
        }

    def _save_settings(self, body: Any) -> None:
        if not isinstance(body, dict) or not isinstance(body.get("settings"), dict):
            self._error(400, "A settings object is required.")
            return
        try:
            STATE.settings = normalize_settings(body["settings"])
        except SettingsError as exc:
            self._error(400, str(exc))
            return
        self._json({"result": self._settings_payload()})

    def _verify(self, body: Any) -> None:
        token = str(body.get("token") or "").strip()
        workflow_id = str(body.get("workflowId") or "").strip()
        if not token:
            self._json(
                {
                    "result": {
                        "valid": False,
                        "httpStatus": 401,
                        "message": "A bearer token is required.",
                    }
                }
            )
            return
        if not workflow_id:
            self._json(
                {
                    "result": {
                        "valid": False,
                        "httpStatus": 400,
                        "message": "A workflow ID is required.",
                    }
                }
            )
            return
        if token.lower() == "bad":
            self._json(
                {
                    "result": {
                        "valid": False,
                        "httpStatus": 401,
                        "message": "Invalid bearer token.",
                    }
                }
            )
            return
        self._json(
            {
                "result": {
                    "valid": True,
                    "httpStatus": 200,
                    "name": "Development workflow",
                    "status": "active",
                    "message": "Workflow found.",
                }
            }
        )

    def _test(self, body: Any) -> None:
        event_key = str(body.get("eventKey") or "")
        token = str(body.get("token") or "").strip()
        workflow_id = str(body.get("workflowId") or "").strip()
        if event_key not in EVENT_DEFINITIONS_BY_KEY:
            self._error(400, "Unknown event: %s" % event_key)
            return
        if not token:
            self._json(
                {
                    "result": {
                        "ok": False,
                        "httpStatus": 401,
                        "message": "A bearer token is required.",
                    }
                }
            )
            return
        if not workflow_id:
            self._json(
                {
                    "result": {
                        "ok": False,
                        "httpStatus": 400,
                        "message": "A workflow ID is required.",
                    }
                }
            )
            return
        if token.lower() == "bad":
            self._json(
                {
                    "result": {
                        "ok": False,
                        "httpStatus": 401,
                        "message": "Invalid bearer token.",
                    }
                }
            )
            return

        STATE.last_send = {
            "at": _utc_now(),
            "eventKey": event_key,
            "kind": EVENT_DEFINITIONS_BY_KEY[event_key]["kind"],
            "ok": True,
            "httpStatus": 202,
            "message": "Accepted (mock).",
        }
        self._json(
            {
                "result": {
                    "ok": True,
                    "httpStatus": 202,
                    "message": "Accepted (mock).",
                }
            }
        )

    def _update(self, body: Any) -> None:
        action = str(body.get("action") or "update").strip().lower()
        if action not in ("refresh", "force_refresh", "update"):
            self._error(400, "Unknown update action: %s" % action)
            return
        self._json(
            {
                "result": {
                    "started": False,
                    "reinstalled": False,
                    "status": STATE.update_state(),
                }
            }
        )

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            self._error(400, "Request body must be valid JSON.")
            return None

    def _serve_static(self, name: str) -> None:
        candidate = (STATIC_DIR / name).resolve()
        if STATIC_DIR.resolve() not in candidate.parents or not candidate.is_file():
            self._error(404, "Not found.")
            return
        content = candidate.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            CONTENT_TYPES.get(candidate.suffix.lower(), "application/octet-stream"),
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload: Any, status: int = 200) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": {"message": message, "code": status}}, status)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[dev] %s - %s\n" % (self.address_string(), fmt % args))


def _utc_now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DevHandler)
    url = "http://%s:%d/server/notifyecho/ui" % (args.host, args.port)
    print("NotifyEcho dev UI: %s" % url)
    print("Mock endpoints only; no Klipper, Moonraker, NotifyEcho, or git.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
