import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from installer import InstallResult  # noqa: E402
from security import SecurityError  # noqa: E402
from worker import DownloadInstallWorker  # noqa: E402


class _Security:
    """SecurityManager'ın worker tarafından kullanılan yüzeyi."""

    def __init__(self, verify_error=None):
        self.verify_error = verify_error
        self.verified = []

    def validate_url(self, _url):
        return None

    def verify_download(self, path, component):
        self.verified.append((path, component.get("name")))
        if self.verify_error:
            raise self.verify_error
        return "sha256"


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


class VerificationPipelineTests(unittest.TestCase):
    """İndirme → doğrulama → kurulum zincirinin güvenlik kapısı."""

    COMPONENT = {
        "name": "VC++ Redist 2015-2022 (x64)",
        "url": "https://example.com/vc_redist.x64.exe",
        "sha256": "0" * 64,
        "evergreen": True,
        "publisher": "Microsoft Corporation",
    }

    def _run(self, security, downloaded_path):
        worker = DownloadInstallWorker([dict(self.COMPONENT)], security)
        errors = []
        worker.signals.component_error.connect(lambda *args: errors.append(args))
        with (
            patch("worker.get_cache_dir", return_value=str(ROOT)),
            patch("worker.find_cached", return_value=None),
            patch("worker.download_file", return_value=downloaded_path),
            patch(
                "worker.install_component",
                return_value=InstallResult("VC++ Redist 2015-2022 (x64)", 0, True),
            ) as install,
            patch("worker.os.path.exists", return_value=False),
        ):
            worker.run()
        return errors, install

    def test_component_is_passed_whole_so_publisher_rules_apply(self):
        """Doğrulayıcı yalnızca hash'i değil, bileşenin tamamını görmeli."""
        security = _Security()
        self._run(security, str(ROOT / "vc_redist.x64.exe"))
        self.assertEqual(
            security.verified,
            # bir kez indirmeden sonra, bir kez kurulumdan hemen önce
            [(str(ROOT / "vc_redist.x64.exe"), "VC++ Redist 2015-2022 (x64)")] * 2,
        )

    def test_unverifiable_file_is_never_installed(self):
        security = _Security(verify_error=SecurityError("imza doğrulanamadı"))
        errors, install = self._run(security, str(ROOT / "vc_redist.x64.exe"))
        install.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIn("VC++ Redist 2015-2022 (x64)", errors[0][0])

    def test_evergreen_failure_message_mentions_both_checks(self):
        security = _Security(verify_error=SecurityError("detay"))
        errors, _install = self._run(security, str(ROOT / "vc_redist.x64.exe"))
        message = errors[0][1]
        self.assertIn("checksum", message)
        self.assertIn("Microsoft Corporation", message)


if __name__ == "__main__":
    unittest.main()
