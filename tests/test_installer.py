from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRANCH = "main"


@unittest.skipUnless(shutil.which("git"), "git is required")
class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / "home"
        self.data = self.root / "printer_data"
        self.install = self.root / "notifyecho_mainsail"
        self.source = self.root / "source"
        self.config = self.data / "config" / "moonraker.conf"
        self.navi = self.data / "config" / ".theme" / "navi.json"

        (self.home / "moonraker" / "moonraker" / "components").mkdir(parents=True)
        shutil.copytree(
            ROOT,
            self.source,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".pytest_cache"),
        )
        subprocess.run(["git", "init", "-b", BRANCH], cwd=self.source, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=self.source, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=NotifyEcho Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-m",
                "test snapshot",
            ],
            cwd=self.source,
            check=True,
            capture_output=True,
        )
        self.config.parent.mkdir(parents=True)
        self.config.write_text(
            "[server]\nhost: 0.0.0.0\n\n[update_manager]\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _env(self) -> dict[str, str]:
        return {**os.environ, "HOME": str(self.home)}

    def _run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(ROOT / script), *args],
            cwd=ROOT,
            env=self._env(),
            text=True,
            capture_output=True,
            check=True,
        )

    def _install(self) -> None:
        self._run(
            "install.sh",
            "--no-restart",
            "--data-dir",
            str(self.data),
            "--install-dir",
            str(self.install),
            "--repo-url",
            self.source.as_uri(),
            "--branch",
            BRANCH,
        )

    def test_install_is_idempotent_and_uninstalls(self) -> None:
        components = self.home / "moonraker" / "moonraker" / "components"
        target = components / "notifyecho"

        self._install()
        self._install()

        self.assertTrue(target.is_symlink())
        self.assertEqual(target.resolve(), (self.install / "moonraker_component" / "notifyecho").resolve())

        config = self.config.read_text(encoding="utf-8")
        self.assertEqual(config.count("[notifyecho]"), 1)
        self.assertEqual(config.count("[update_manager notifyecho]"), 1)
        self.assertIn("managed_services: moonraker", config)
        self.assertNotIn("system_dependencies", config)

        navi = json.loads(self.navi.read_text(encoding="utf-8"))
        entries = [item for item in navi if item.get("href") == "/server/notifyecho/ui"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "NotifyEcho")

        self._run(
            "uninstall.sh",
            "--no-restart",
            "--data-dir",
            str(self.data),
            "--install-dir",
            str(self.install),
        )

        self.assertFalse(target.exists())
        config = self.config.read_text(encoding="utf-8")
        self.assertNotIn("[notifyecho]", config)
        self.assertNotIn("[update_manager notifyecho]", config)
        navi = json.loads(self.navi.read_text(encoding="utf-8"))
        self.assertEqual(
            [item for item in navi if item.get("href") == "/server/notifyecho/ui"],
            [],
        )

    def test_install_refreshes_existing_update_manager_section(self) -> None:
        self._install()
        config = self.config.read_text(encoding="utf-8")
        config = config.replace("managed_services: moonraker\n", "")
        self.config.write_text(config, encoding="utf-8")

        self._install()

        config = self.config.read_text(encoding="utf-8")
        self.assertEqual(config.count("[update_manager notifyecho]"), 1)
        self.assertIn("managed_services: moonraker", config)


if __name__ == "__main__":
    unittest.main()
