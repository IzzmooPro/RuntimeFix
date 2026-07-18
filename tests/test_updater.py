import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from updater import (  # noqa: E402
    UpdateError,
    _digest_matches,
    _pick_setup_asset,
    _safe_filename,
    _validate_update_url,
    download_update,
    is_newer_version,
)


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(is_newer_version("2.5", "2.4"))
        self.assertTrue(is_newer_version("v2.3.1", "2.3"))
        self.assertFalse(is_newer_version("2.3", "2.3.0"))
        self.assertFalse(is_newer_version("2.2", "2.3"))
        self.assertTrue(is_newer_version("3.0.1", "3.0.0"))
        for invalid in ("3", "release-3.0.0", "3.0.0-beta", ""):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError):
                is_newer_version(invalid, "3.0.0")

    def test_digest_is_required_and_must_be_sha256(self):
        payload = b"RuntimeFix updater test"
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "setup.exe"
            path.write_bytes(payload)

            self.assertTrue(_digest_matches(str(path), f"sha256:{expected}"))
            self.assertFalse(_digest_matches(str(path), None))
            self.assertFalse(_digest_matches(str(path), ""))
            self.assertFalse(_digest_matches(str(path), f"sha1:{expected}"))
            self.assertFalse(_digest_matches(str(path), "sha256:1234"))
            self.assertFalse(_digest_matches(str(path), f"sha256:{'0' * 64}"))

    def test_asset_filename_is_sanitized(self):
        self.assertEqual(
            _safe_filename('RuntimeFix:Setup/2.5?.exe'),
            "RuntimeFix_Setup_2.5_.exe",
        )

    def test_only_exact_setup_asset_is_selected(self):
        assets = [
            {
                "name": "Other-Setup-3.0.0.exe",
                "browser_download_url": "https://github.com/other.exe",
            },
            {
                "name": "RuntimeFix-Setup-3.0.0.exe",
                "browser_download_url": "https://github.com/runtimefix.exe",
            },
        ]
        self.assertEqual(
            _pick_setup_asset(assets, "3.0.0"),
            assets[1],
        )
        self.assertIsNone(_pick_setup_asset(assets, "3.0.1"))

    def test_update_urls_are_restricted_to_github_hosts(self):
        for url in (
            "https://api.github.com/repos/IzzmooPro/RuntimeFix/releases/latest",
            "https://github.com/IzzmooPro/RuntimeFix/releases/download/v3.0.0/a.exe",
            "https://release-assets.githubusercontent.com/file",
        ):
            _validate_update_url(url)
        for url in (
            "http://github.com/file.exe",
            "https://github.com.evil.test/file.exe",
            "https://example.com/file.exe",
        ):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                _validate_update_url(url)

    def test_download_rejects_untrusted_redirect_and_removes_partial_file(self):
        class FakeResponse:
            headers = {"Content-Length": "4"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://evil.test/setup.exe"

            def read(self, _size):
                return b"data"

        info = {
            "version": "3.0.0",
            "asset_name": "RuntimeFix-Setup-3.0.0.exe",
            "download_url": "https://github.com/setup.exe",
            "digest": "sha256:" + "0" * 64,
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, patch(
            "updater.urllib.request.urlopen",
            return_value=FakeResponse(),
        ):
            with self.assertRaises(UpdateError):
                download_update(info, directory)
            self.assertFalse(any(Path(directory).iterdir()))


if __name__ == "__main__":
    unittest.main()
