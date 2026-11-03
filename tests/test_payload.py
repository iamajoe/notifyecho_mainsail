from __future__ import annotations

import datetime
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "moonraker_component"))

from notifyecho.payload import build_notify_request, format_duration  # noqa: E402
from notifyecho.settings import EVENT_DEFINITIONS, KIND_BY_KEY  # noqa: E402

PRINTER = {"hostname": "voron", "port": 7125, "moonrakerVersion": "v0.0.0"}
NOW = datetime.datetime(2026, 11, 3, 12, 0, 0, tzinfo=datetime.timezone.utc)
STATS = {
    "state": "complete",
    "filename": "benchy.gcode",
    "print_duration": 4321.2,
    "total_duration": 4380.0,
    "filament_used": 12345.6,
    "info": {"current_layer": 120, "total_layer": 120},
}


class BuildRequestTest(unittest.TestCase):
    def test_every_event_has_title_and_message(self) -> None:
        for definition in EVENT_DEFINITIONS:
            with self.subTest(event=definition["key"]):
                payload = build_notify_request(
                    definition["key"],
                    definition["kind"],
                    print_stats=STATS,
                    prev_stats={"state": "printing", "filename": "benchy.gcode"},
                    printer_info=PRINTER,
                    now=NOW,
                )
                self.assertEqual(payload["kind"], definition["kind"])
                self.assertTrue(payload["content"]["title"].strip())
                self.assertTrue(payload["content"]["message"].strip())

    def test_print_complete_payload(self) -> None:
        payload = build_notify_request(
            "print_complete",
            KIND_BY_KEY["print_complete"],
            print_stats=STATS,
            prev_stats={"state": "printing"},
            printer_info=PRINTER,
            now=NOW,
        )

        self.assertEqual(payload["kind"], "klipper.job_state.complete")
        self.assertEqual(payload["content"]["title"], "Print complete")
        self.assertIn("benchy.gcode", payload["content"]["message"])
        self.assertIn("1h 12m", payload["content"]["message"])
        self.assertEqual(payload["content"]["data"]["filename"], "benchy.gcode")
        self.assertEqual(payload["content"]["data"]["layers"]["current"], 120)
        self.assertEqual(payload["metadata"]["source"], "mainsail")
        self.assertEqual(payload["metadata"]["timestamp"], "2026-11-03T12:00:00Z")
        self.assertEqual(payload["metadata"]["printer"]["hostname"], "voron")
        self.assertIn("klipper", payload["options"]["tags"])

    def test_progress_payload(self) -> None:
        payload = build_notify_request(
            "print_progress",
            KIND_BY_KEY["print_progress"],
            print_stats={"state": "printing", "filename": "part.gcode"},
            printer_info=PRINTER,
            extra={"progress": 0.5, "milestone": 50},
            now=NOW,
        )

        self.assertEqual(payload["content"]["data"]["milestone"], 50)
        self.assertEqual(payload["content"]["data"]["progress"], 0.5)
        self.assertIn("50%", payload["content"]["message"])

    def test_error_payload(self) -> None:
        payload = build_notify_request(
            "error",
            KIND_BY_KEY["error"],
            printer_info=PRINTER,
            extra={"error": "Klipper disconnected", "errorSource": "klippy_disconnect"},
            now=NOW,
        )

        self.assertEqual(payload["content"]["title"], "Klipper error")
        self.assertIn("Klipper disconnected", payload["content"]["message"])
        self.assertEqual(payload["metadata"]["errorSource"], "klippy_disconnect")

    def test_missing_stats_still_produces_valid_content(self) -> None:
        payload = build_notify_request(
            "print_complete", KIND_BY_KEY["print_complete"], now=NOW
        )

        self.assertTrue(payload["content"]["title"])
        self.assertTrue(payload["content"]["message"])
        self.assertNotIn("printStats", payload["metadata"])


class FormatDurationTest(unittest.TestCase):
    def test_formats(self) -> None:
        cases = [
            (0, "less than a minute"),
            (42, "42s"),
            (60, "1m"),
            (4320, "1h 12m"),
            (None, "unknown time"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_duration(value), expected)


if __name__ == "__main__":
    unittest.main()
