from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict

USER_AGENT = "NotifyEcho-Mainsail/0.1"


@dataclass
class SendResult:
    ok: bool
    status_code: int
    message: str
    body: str = ""
    workflow_id: str = ""


@dataclass
class VerifyResult:
    valid: bool
    status_code: int
    message: str
    name: str = ""
    status: str = ""


class NotifyEchoClient:
    """Thin wrapper around Moonraker's http_client for the NotifyEcho API."""

    def __init__(self, http_client: Any) -> None:
        self.http = http_client

    async def send(
        self,
        base_url: str,
        token: str,
        workflow_id: str,
        payload: Dict[str, Any],
    ) -> SendResult:
        url = _notify_url(base_url, workflow_id)
        headers = {
            "Authorization": "Bearer %s" % token.strip(),
            "Idempotency-Key": uuid.uuid4().hex,
            "User-Agent": USER_AGENT,
        }
        try:
            response = await self.http.post(
                url,
                body=payload,
                headers=headers,
                connect_timeout=5.0,
                request_timeout=15.0,
                attempts=2,
            )
        except Exception as exc:  # Network failures should not break the event loop.
            return SendResult(False, 0, str(exc), workflow_id=workflow_id)

        body = _decode_body(response.body)
        if 200 <= response.code < 300:
            return SendResult(True, response.code, "Accepted", body, workflow_id)

        return SendResult(
            False,
            response.code,
            _error_message(body, response.code),
            body,
            workflow_id,
        )

    async def verify(
        self,
        base_url: str,
        token: str,
        workflow_id: str,
    ) -> VerifyResult:
        url = _status_url(base_url, workflow_id)
        headers = {
            "Authorization": "Bearer %s" % token.strip(),
            "User-Agent": USER_AGENT,
        }
        try:
            response = await self.http.request(
                "GET",
                url,
                headers=headers,
                connect_timeout=5.0,
                request_timeout=15.0,
                enable_cache=False,
            )
        except Exception as exc:
            return VerifyResult(False, 0, str(exc))

        body = _decode_body(response.body)
        if response.code == 200:
            try:
                data = json.loads(body) if body else {}
            except ValueError:
                data = {}
            return VerifyResult(
                True,
                200,
                "Workflow found.",
                _as_string(data.get("name")),
                _as_string(data.get("status")),
            )

        return VerifyResult(
            False,
            response.code,
            _verify_error_message(response.code, body),
        )


def _notify_url(base_url: str, workflow_id: str) -> str:
    return "%s/api/notify/%s" % (base_url.rstrip("/"), workflow_id)


def _status_url(base_url: str, workflow_id: str) -> str:
    return "%s/api/notify/%s/status" % (base_url.rstrip("/"), workflow_id)


def _decode_body(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _verify_error_message(status_code: int, body: str) -> str:
    if status_code == 401:
        return "Invalid bearer token."
    if status_code == 404:
        return "Workflow not found for this token."
    if status_code == 429:
        return "Rate limited by NotifyEcho; try again in a moment."
    if status_code == 0:
        return body or "Could not reach NotifyEcho."
    return _error_message(body, status_code)


def _error_message(body: str, status_code: int) -> str:
    if body:
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return _as_string(message)
                code = error.get("code")
                if code:
                    return _as_string(code)
            if isinstance(error, str) and error:
                return error
            message = data.get("message")
            if message:
                return _as_string(message)
    if status_code:
        return "NotifyEcho returned HTTP %d." % status_code
    return "NotifyEcho request failed."


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)
