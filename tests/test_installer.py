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
TAG = "v0.1.0"


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
        subprocess.run(
            ["git", "tag", TAG], cwd=self.source, check=True, capture_output=True
        )

        # The production installer targets the GitHub repo. Point a copy at the
        # temporary source repo so the install flow can be tested offline.
        self.installer = self.root / "install.sh"
        installer_text = (ROOT / "install.sh").read_text(encoding="utf-8")
        installer_text = installer_text.replace(
            'REPO_URL="https://github.com/iamajoe/notifyecho_mainsail.git"',
            'REPO_URL="%s"' % self.source.as_uri(),
        )
        self.assertIn(self.source.as_uri(), installer_text)
        self.installer.write_text(installer_text, encoding="utf-8")

        self.config.parent.mkdir(parents=True)
        self.config.write_text(
            "[server]\nhost: 0.0.0.0\n\n[update_manager]\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _env(self) -> dict[str, str]:
        return {**os.environ, "HOME": str(self.home)}

    def _run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        script_path = pathlib.Path(script)
        if not script_path.is_absolute():
            script_path = ROOT / script_path
        return subprocess.run(
            ["bash", str(script_path), *args],
            cwd=ROOT,
            env=self._env(),
            text=True,
            capture_output=True,
            check=True,
        )

    def _install(self, use_tag: bool = True) -> None:
        args = [
            "--no-restart",
            "--data-dir",
            str(self.data),
            "--install-dir",
            str(self.install),
        ]
        if use_tag:
            args.extend(["--tag", TAG])
        self._run(self.installer, *args)

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.install), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

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
        self.assertIn("channel: stable", config)
        self.assertIn("managed_services: moonraker", config)
        self.assertNotIn("system_dependencies", config)

        self.assertEqual(self._git("describe", "--tags", "--exact-match"), TAG)
        self.assertEqual(self._git("symbolic-ref", "--short", "HEAD"), BRANCH)
        self.assertEqual(
            self._git("rev-parse", "HEAD"),
            subprocess.run(
                ["git", "-C", str(self.source), "rev-parse", TAG],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        )

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

    def test_install_uses_latest_tag_by_default(self) -> None:
        readme = self.source / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + "\nLatest tag test.\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=self.source,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=NotifyEcho Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-m",
                "newer release",
            ],
            cwd=self.source,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "tag", "v0.1.1"], cwd=self.source, check=True, capture_output=True
        )

        self._install(use_tag=False)

        self.assertEqual(self._git("describe", "--tags", "--exact-match"), "v0.1.1")

    def test_install_requires_a_tag(self) -> None:
        subprocess.run(
            ["git", "tag", "-d", TAG], cwd=self.source, check=True, capture_output=True
        )

        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self._install(use_tag=False)

        self.assertIn("No release tags found", raised.exception.stderr)

    def test_install_rejects_non_semver_tag(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self._run(
                self.installer,
                "--no-restart",
                "--data-dir",
                str(self.data),
                "--install-dir",
                str(self.install),
                "--tag",
                "main",
            )

        self.assertIn("must look like vX.Y.Z", raised.exception.stderr)


if __name__ == "__main__":
    unittest.main()
