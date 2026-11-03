from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

DEFAULT_BASE_URL = "https://notifyecho.com"
DEFAULT_PROGRESS_MILESTONES: Tuple[int, ...] = (25, 50, 75, 90)
MAX_PROGRESS_MILESTONES = 20

# The event catalog is the single source of truth shared by the component, the
# settings UI and tests. Kinds are dot-separated because NotifyEcho's own
# trigger names follow that style (e.g. "deploy.failed").
EVENT_DEFINITIONS: Tuple[Dict[str, str], ...] = (
    {
        "key": "print_started",
        "kind": "klipper.job_state.started",
        "label": "Print started",
        "description": "Klipper started a print job.",
        "source": "job_state:started",
    },
    {
        "key": "print_paused",
        "kind": "klipper.job_state.paused",
        "label": "Print paused",
        "description": "Klipper paused the current print job.",
        "source": "job_state:paused",
    },
    {
        "key": "print_resumed",
        "kind": "klipper.job_state.resumed",
        "label": "Print resumed",
        "description": "Klipper resumed the current print job.",
        "source": "job_state:resumed",
    },
    {
        "key": "print_complete",
        "kind": "klipper.job_state.complete",
        "label": "Print complete",
        "description": "The print job finished successfully.",
        "source": "job_state:complete",
    },
    {
        "key": "print_cancelled",
        "kind": "klipper.job_state.cancelled",
        "label": "Print cancelled",
        "description": "The print job was cancelled.",
        "source": "job_state:cancelled",
    },
    {
        "key": "print_failed",
        "kind": "klipper.job_state.failed",
        "label": "Print failed",
        "description": "Klipper reported a print failure.",
        "source": "job_state:error",
    },
    {
        "key": "print_progress",
        "kind": "klipper.job_state.progress",
        "label": "Print progress",
        "description": "The print job crossed a configured progress milestone.",
        "source": "virtual_sdcard progress",
    },
    {
        "key": "ready",
        "kind": "klipper.ready",
        "label": "Printer ready",
        "description": "Klipper became ready.",
        "source": "server:klippy_ready",
    },
    {
        "key": "shutdown",
        "kind": "klipper.shutdown",
        "label": "Printer shutdown",
        "description": "Klipper entered the shutdown state.",
        "source": "server:klippy_shutdown",
    },
    {
        "key": "error",
        "kind": "klipper.error",
        "label": "System error",
        "description": "Klipper, Moonraker or the plugin reported a system error.",
        "source": "klippy error / disconnect / plugin",
    },
)

EVENT_DEFINITIONS_BY_KEY: Dict[str, Dict[str, str]] = {
    item["key"]: item for item in EVENT_DEFINITIONS
}
EVENT_KEYS: Tuple[str, ...] = tuple(item["key"] for item in EVENT_DEFINITIONS)
KIND_BY_KEY: Dict[str, str] = {
    item["key"]: item["kind"] for item in EVENT_DEFINITIONS
}


class SettingsError(ValueError):
    """Raised when stored or submitted settings are invalid."""


def default_settings() -> Dict[str, Any]:
    return {
        "baseUrl": DEFAULT_BASE_URL,
        "token": "",
        "defaultWorkflowId": "",
        "advancedMode": False,
        "progressMilestones": list(DEFAULT_PROGRESS_MILESTONES),
        "events": {
            key: {"enabled": True, "workflowId": ""} for key in EVENT_KEYS
        },
    }


def normalize_settings(raw: Optional[Any]) -> Dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SettingsError("Settings must be an object.")

    base_url = normalize_base_url(raw.get("baseUrl", DEFAULT_BASE_URL))
    token = _as_string(raw.get("token", ""))
    default_workflow = normalize_uuid(
        raw.get("defaultWorkflowId", ""), "Default workflow ID"
    )
    advanced_mode = _as_bool(raw.get("advancedMode", False), False)
    milestones = normalize_milestones(
        raw.get("progressMilestones", DEFAULT_PROGRESS_MILESTONES)
    )

    raw_events = raw.get("events", {})
    if raw_events is None:
        raw_events = {}
    if not isinstance(raw_events, dict):
        raise SettingsError("Events must be an object.")

    events: Dict[str, Dict[str, Any]] = {}
    for key in EVENT_KEYS:
        entry = raw_events.get(key, {})
        if entry is None:
            entry = {}
        if not isinstance(entry, dict):
            raise SettingsError("Event '%s' must be an object." % key)
        events[key] = {
            "enabled": _as_bool(entry.get("enabled", True), True),
            "workflowId": normalize_uuid(
                entry.get("workflowId", ""), "Workflow ID for %s" % key
            ),
        }

    return {
        "baseUrl": base_url,
        "token": token,
        "defaultWorkflowId": default_workflow,
        "advancedMode": advanced_mode,
        "progressMilestones": milestones,
        "events": events,
    }


def normalize_base_url(value: Any) -> str:
    text = _as_string(value).strip()
    if not text:
        text = DEFAULT_BASE_URL
    text = text.rstrip("/")
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise SettingsError("NotifyEcho URL must start with http:// or https://.")
    if parts.query or parts.fragment:
        raise SettingsError("NotifyEcho URL must not contain a query or fragment.")
    return text


def normalize_uuid(value: Any, label: str) -> str:
    text = _as_string(value).strip()
    if not text:
        return ""
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError):
        raise SettingsError("%s must be a valid UUID." % label)


def normalize_milestones(value: Any) -> List[int]:
    if value is None:
        parts: Sequence[Any] = DEFAULT_PROGRESS_MILESTONES
    elif isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = value
    else:
        raise SettingsError("Progress milestones must be a list or comma-separated string.")

    milestones: List[int] = []
    for part in parts:
        if isinstance(part, bool):
            raise SettingsError("Progress milestones must be whole numbers.")
        if isinstance(part, str):
            part = part.strip()
            if not part:
                continue
            try:
                number = int(part)
            except ValueError:
                raise SettingsError("Progress milestones must be whole numbers.")
        elif isinstance(part, int):
            number = part
        else:
            raise SettingsError("Progress milestones must be whole numbers.")
        if number < 1 or number > 100:
            raise SettingsError("Progress milestones must be between 1 and 100.")
        if number not in milestones:
            milestones.append(number)

    if len(milestones) > MAX_PROGRESS_MILESTONES:
        raise SettingsError("Too many progress milestones (maximum %d)." % MAX_PROGRESS_MILESTONES)

    milestones.sort()
    return milestones


def is_event_enabled(settings: Dict[str, Any], event_key: str) -> bool:
    entry = settings.get("events", {}).get(event_key)
    if not isinstance(entry, dict):
        return True
    return bool(entry.get("enabled", True))


def resolve_workflow_id(settings: Dict[str, Any], event_key: str) -> str:
    if settings.get("advancedMode"):
        entry = settings.get("events", {}).get(event_key, {})
        if isinstance(entry, dict):
            workflow_id = _as_string(entry.get("workflowId", "")).strip()
            if workflow_id:
                return workflow_id
    return _as_string(settings.get("defaultWorkflowId", "")).strip()


def event_catalog() -> List[Dict[str, str]]:
    return copy.deepcopy(list(EVENT_DEFINITIONS))


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
