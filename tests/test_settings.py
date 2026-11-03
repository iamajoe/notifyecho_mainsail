from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "moonraker_component"))

from notifyecho.settings import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_PROGRESS_MILESTONES,
    EVENT_KEYS,
    SettingsError,
    default_settings,
    is_event_enabled,
    normalize_base_url,
    normalize_milestones,
    normalize_settings,
    normalize_uuid,
    resolve_workflow_id,
)


class DefaultSettingsTest(unittest.TestCase):
    def test_all_events_enabled_by_default(self) -> None:
        settings = default_settings()

        self.assertEqual(len(settings["events"]), len(EVENT_KEYS))
        for key in EVENT_KEYS:
            self.assertTrue(settings["events"][key]["enabled"])

    def test_defaults(self) -> None:
        settings = default_settings()

        self.assertEqual(settings["baseUrl"], DEFAULT_BASE_URL)
        self.assertEqual(settings["token"], "")
        self.assertEqual(settings["defaultWorkflowId"], "")
        self.assertFalse(settings["advancedMode"])
        self.assertEqual(
            settings["progressMilestones"], list(DEFAULT_PROGRESS_MILESTONES)
        )


class NormalizeSettingsTest(unittest.TestCase):
    def test_empty_input_uses_defaults(self) -> None:
        settings = normalize_settings({})

        self.assertEqual(settings["baseUrl"], DEFAULT_BASE_URL)
        self.assertEqual(settings["progressMilestones"], list(DEFAULT_PROGRESS_MILESTONES))
        self.assertTrue(settings["events"]["print_complete"]["enabled"])

    def test_round_trip(self) -> None:
        raw = {
            "baseUrl": "https://example.test/",
            "token": "pk_live_abc",
            "defaultWorkflowId": "11111111-1111-1111-1111-111111111111",
            "advancedMode": True,
            "progressMilestones": [10, 50, 10, 90],
            "events": {
                "print_complete": {
                    "enabled": False,
                    "workflowId": "22222222-2222-2222-2222-222222222222",
                }
            },
        }

        settings = normalize_settings(raw)

        self.assertEqual(settings["baseUrl"], "https://example.test")
        self.assertEqual(settings["token"], "pk_live_abc")
        self.assertTrue(settings["advancedMode"])
        self.assertEqual(settings["progressMilestones"], [10, 50, 90])
        self.assertFalse(settings["events"]["print_complete"]["enabled"])
        self.assertEqual(
            settings["events"]["print_complete"]["workflowId"],
            "22222222-2222-2222-2222-222222222222",
        )

    def test_unknown_events_are_ignored(self) -> None:
        settings = normalize_settings({"events": {"not_real": {"enabled": False}}})

        self.assertNotIn("not_real", settings["events"])

    def test_invalid_base_url(self) -> None:
        for value in ("ftp://example.test", "example.test", "https://"):
            with self.subTest(value=value):
                with self.assertRaises(SettingsError):
                    normalize_settings({"baseUrl": value})

    def test_invalid_uuid(self) -> None:
        with self.assertRaises(SettingsError):
            normalize_settings({"defaultWorkflowId": "not-a-uuid"})

    def test_events_must_be_object(self) -> None:
        with self.assertRaises(SettingsError):
            normalize_settings({"events": []})

    def test_event_must_be_object(self) -> None:
        with self.assertRaises(SettingsError):
            normalize_settings({"events": {"print_complete": "yes"}})


class HelpersTest(unittest.TestCase):
    def test_normalize_uuid_returns_canonical_form(self) -> None:
        self.assertEqual(
            normalize_uuid("{11111111-1111-1111-1111-111111111111}", "ID"),
            "11111111-1111-1111-1111-111111111111",
        )

    def test_empty_uuid_is_allowed(self) -> None:
        self.assertEqual(normalize_uuid("", "ID"), "")

    def test_milestones_from_string(self) -> None:
        self.assertEqual(normalize_milestones("25, 50, 25, 75"), [25, 50, 75])

    def test_milestones_reject_out_of_range(self) -> None:
        for value in ([0], [101], ["abc"]):
            with self.subTest(value=value):
                with self.assertRaises(SettingsError):
                    normalize_milestones(value)

    def test_base_url_trims_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_base_url("https://notifyecho.com/"), "https://notifyecho.com"
        )

    def test_advanced_workflow_falls_back_to_default(self) -> None:
        settings = default_settings()
        settings["advancedMode"] = True
        settings["defaultWorkflowId"] = "11111111-1111-1111-1111-111111111111"

        self.assertEqual(
            resolve_workflow_id(settings, "print_complete"),
            "11111111-1111-1111-1111-111111111111",
        )

    def test_advanced_uses_event_workflow(self) -> None:
        settings = default_settings()
        settings["advancedMode"] = True
        settings["defaultWorkflowId"] = "11111111-1111-1111-1111-111111111111"
        settings["events"]["print_complete"]["workflowId"] = (
            "22222222-2222-2222-2222-222222222222"
        )

        self.assertEqual(
            resolve_workflow_id(settings, "print_complete"),
            "22222222-2222-2222-2222-222222222222",
        )

    def test_default_mode_ignores_event_workflow(self) -> None:
        settings = default_settings()
        settings["defaultWorkflowId"] = "11111111-1111-1111-1111-111111111111"
        settings["events"]["print_complete"]["workflowId"] = (
            "22222222-2222-2222-2222-222222222222"
        )

        self.assertEqual(
            resolve_workflow_id(settings, "print_complete"),
            "11111111-1111-1111-1111-111111111111",
        )

    def test_event_enabled(self) -> None:
        settings = default_settings()

        self.assertTrue(is_event_enabled(settings, "print_complete"))
        settings["events"]["print_complete"]["enabled"] = False
        self.assertFalse(is_event_enabled(settings, "print_complete"))


if __name__ == "__main__":
    unittest.main()
