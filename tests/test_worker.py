import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from installer import InstallResult  # noqa: E402
from worker import DownloadInstallWorker  # noqa: E402


class _Security:
    def validate_url(self, _url):
        return None

    def verify_sha256(self, _path, _digest):
        return None


class WorkerTests(unittest.TestCase):
    def test_skipped_install_is_reported_as_failure(self):
        component = {
            "name": "Example",
            "url": "https://example.com/setup.zip",
            "sha256": "0" * 64,
        }
        worker = DownloadInstallWorker([component], _Security())
        errors = []
        finished = []
        worker.signals.component_error.connect(lambda *args: errors.append(args))
        worker.signals.finished.connect(finished.append)
        with (
            patch("worker.get_cache_dir", return_value=str(ROOT)),
            patch("worker.find_cached", return_value=None),
            patch("worker.download_file", return_value=str(ROOT / "setup.zip")),
            patch(
                "worker.install_component",
                return_value=InstallResult(
                    "Example",
                    -1,
                    False,
                    skipped=True,
                    message="Manual install required.",
                ),
            ),
        ):
            worker.run()
        self.assertEqual(errors, [("Example", "Manual install required.")])
        self.assertEqual(finished, [False])

    def test_unexpected_component_error_does_not_abort_following_component(self):
        components = [
            {
                "name": "Broken",
                "url": "https://example.com/broken.exe",
                "sha256": "0" * 64,
            },
            {
                "name": "Working",
                "url": "https://example.com/working.exe",
                "sha256": "1" * 64,
            },
        ]
        worker = DownloadInstallWorker(components, _Security())
        successes = []
        errors = []
        finished = []
        worker.signals.component_success.connect(successes.append)
        worker.signals.component_error.connect(lambda *args: errors.append(args))
        worker.signals.finished.connect(finished.append)
        with (
            patch("worker.get_cache_dir", return_value=str(ROOT)),
            patch("worker.find_cached", return_value=None),
            patch(
                "worker.download_file",
                side_effect=[str(ROOT / "broken.exe"), str(ROOT / "working.exe")],
            ),
            patch(
                "worker.install_component",
                side_effect=[
                    RuntimeError("boom"),
                    InstallResult("Working", 0, True),
                ],
            ),
        ):
            worker.run()
        self.assertEqual(successes, ["Working"])
        self.assertEqual(errors[0][0], "Broken")
        self.assertEqual(finished, [False])


if __name__ == "__main__":
    unittest.main()
