from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

PRINT_EVENT_KEYS = {
    "print_started",
    "print_paused",
    "print_resumed",
    "print_complete",
    "print_cancelled",
    "print_failed",
    "print_progress",
}


def build_notify_request(
    event_key: str,
    kind: str,
    print_stats: Optional[Dict[str, Any]] = None,
    prev_stats: Optional[Dict[str, Any]] = None,
    printer_info: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    stats = print_stats or {}
    previous = prev_stats or {}
    printer = printer_info or {}
    extras = extra or {}

    event_data = _event_data(event_key, stats, printer, extras)
    title, message = _title_and_message(event_key, event_data, printer)
    timestamp = _timestamp(now)

    metadata: Dict[str, Any] = {
        "source": "mainsail",
        "event": event_key,
        "kind": kind,
        "printer": printer,
        "timestamp": timestamp,
    }
    if stats:
        metadata["printStats"] = stats
    if previous:
        metadata["previousPrintStats"] = previous
    for key, value in extras.items():
        metadata[key] = value

    return {
        "kind": kind,
        "content": {
            "title": title,
            "message": message,
            "data": event_data,
        },
        "metadata": metadata,
        "options": {
            "tags": ["klipper", event_key],
        },
    }


def format_duration(seconds: Any) -> str:
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "unknown time"
    if total <= 0:
        return "less than a minute"

    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return "%dh %dm" % (hours, minutes)
    if minutes:
        return "%dm" % minutes
    return "%ds" % total


def _event_data(
    event_key: str,
    stats: Dict[str, Any],
    printer: Dict[str, Any],
    extras: Dict[str, Any],
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "event": event_key,
        "printer": printer.get("hostname") or "printer",
    }

    if event_key in PRINT_EVENT_KEYS:
        filename = _as_string(stats.get("filename"))
        if filename:
            data["filename"] = filename
        state = _as_string(stats.get("state"))
        if state:
            data["state"] = state

        for source_key, target_key in (
            ("print_duration", "printDuration"),
            ("total_duration", "totalDuration"),
            ("filament_used", "filamentUsed"),
        ):
            value = stats.get(source_key)
            if value is not None:
                data[target_key] = value

        info = stats.get("info")
        if isinstance(info, dict):
            layers = {}
            if info.get("current_layer") is not None:
                layers["current"] = info["current_layer"]
            if info.get("total_layer") is not None:
                layers["total"] = info["total_layer"]
            if layers:
                data["layers"] = layers

    for key in ("progress", "milestone", "error", "errorSource"):
        if key in extras and extras[key] is not None:
            data[key] = extras[key]

    return data


def _title_and_message(
    event_key: str,
    event_data: Dict[str, Any],
    printer: Dict[str, Any],
) -> tuple:
    printer_name = _as_string(printer.get("hostname")) or "printer"
    filename = _as_string(event_data.get("filename")) or "the print"

    if event_key == "print_started":
        return "Print started", "%s started on %s." % (filename, printer_name)
    if event_key == "print_paused":
        return "Print paused", "%s paused on %s." % (filename, printer_name)
    if event_key == "print_resumed":
        return "Print resumed", "%s resumed on %s." % (filename, printer_name)
    if event_key == "print_complete":
        duration = format_duration(event_data.get("printDuration"))
        return (
            "Print complete",
            "%s finished in %s on %s." % (filename, duration, printer_name),
        )
    if event_key == "print_cancelled":
        return "Print cancelled", "%s cancelled on %s." % (filename, printer_name)
    if event_key == "print_failed":
        return "Print failed", "%s failed on %s." % (filename, printer_name)
    if event_key == "print_progress":
        milestone = event_data.get("milestone")
        percent = milestone if milestone is not None else _percent(event_data.get("progress"))
        return (
            "Print progress",
            "%s reached %s%% on %s." % (filename, percent, printer_name),
        )
    if event_key == "ready":
        return "Printer ready", "%s is ready." % printer_name
    if event_key == "shutdown":
        return "Printer shutdown", "%s entered the shutdown state." % printer_name
    if event_key == "error":
        message = _as_string(event_data.get("error"))
        if not message:
            message = "%s reported a system error." % printer_name
        return "Klipper error", message

    return "Klipper event", "%s reported %s." % (printer_name, event_key)


def _percent(progress: Any) -> int:
    try:
        return int(round(float(progress) * 100))
    except (TypeError, ValueError):
        return 0


def _timestamp(now: Optional[datetime.datetime]) -> str:
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return now.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)
