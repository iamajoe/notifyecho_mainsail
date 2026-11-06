from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "moonraker_component" / "notifyecho" / "static"


class StaticAssetsTest(unittest.TestCase):
    def test_index_loads_assets(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn("/server/notifyecho/static/app.js", html)
        self.assertIn("/server/notifyecho/static/style.css", html)
        self.assertIn('id="events-list"', html)
        self.assertIn('id="save"', html)
        self.assertIn('id="verify-all"', html)
        self.assertIn('id="update-run"', html)
        self.assertIn('id="update-refresh"', html)

    def test_app_calls_component_endpoints(self) -> None:
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        for endpoint in ("/settings", "/verify", "/test", "/update"):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, script)

    def test_app_exposes_update_controls(self) -> None:
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        self.assertIn("refreshUpdateStatus", script)
        self.assertIn("runUpdate", script)
        self.assertIn("updatePoll", script)
        self.assertIn("updateAllowed", script)

    def test_app_exposes_advanced_routing_and_progress(self) -> None:
        script = (STATIC / "app.js").read_text(encoding="utf-8")

        self.assertIn("advancedMode", script)
        self.assertIn("print_progress", script)
        self.assertIn("milestones", script)

    def test_styles_cover_event_rows(self) -> None:
        css = (STATIC / "style.css").read_text(encoding="utf-8")

        self.assertIn(".event-row", css)
        self.assertIn(".inline-status", css)


if __name__ == "__main__":
    unittest.main()
