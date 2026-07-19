import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from app_info import APP_VERSION  # noqa: E402
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
        self.assertTrue(is_newer_version("3.05", "3.00"))
        self.assertTrue(is_newer_version("3.10", "3.05"))
        self.assertTrue(is_newer_version("v4.00", "3.95"))
        self.assertFalse(is_newer_version("3.05", "3.10"))
        self.assertFalse(is_newer_version("3.00", "3.00"))

    def test_version_ordering_is_correct_past_the_ninth_release(self):
        """Eski gevşek ayrıştırıcıda 3.9 ile 3.05 aynı değere çözülüyordu."""
        self.assertTrue(is_newer_version("3.10", "3.09"))
        self.assertTrue(is_newer_version("3.20", "3.15"))
        self.assertFalse(is_newer_version("3.09", "3.10"))

    def test_ambiguous_and_legacy_version_formats_are_rejected(self):
        # "3.5" → "3.05" ile karışır; "3.0.0" → iki basamak kuralını bozar
        for invalid in ("3.5", "3.0.0", "v2.3.1", "3", "release-3.00",
                        "3.00-beta", ""):
            with self.subTest(invalid=invalid), self.assertRaises(UpdateError):
                is_newer_version(invalid, "3.00")

    def test_shipped_app_version_matches_the_documented_scheme(self):
        """Yanlış biçimli bir APP_VERSION yayınlanırsa güncelleme zinciri kırılır."""
        self.assertRegex(APP_VERSION, re.compile(r"^\d+\.\d{2}$"))
        # Sürüm, updater'ın kendi ayrıştırıcısından da geçmeli
        self.assertFalse(is_newer_version(APP_VERSION, APP_VERSION))

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
                "name": "Other-Setup-3.00.exe",
                "browser_download_url": "https://github.com/other.exe",
            },
            {
                "name": "RuntimeFix-Setup-3.00.exe",
                "browser_download_url": "https://github.com/runtimefix.exe",
            },
        ]
        self.assertEqual(
            _pick_setup_asset(assets, "3.00"),
            assets[1],
        )
        self.assertIsNone(_pick_setup_asset(assets, "3.05"))

    def test_update_urls_are_restricted_to_github_hosts(self):
        for url in (
            "https://api.github.com/repos/IzzmooPro/RuntimeFix/releases/latest",
            "https://github.com/IzzmooPro/RuntimeFix/releases/download/v3.00/a.exe",
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
            "version": "3.00",
            "asset_name": "RuntimeFix-Setup-3.00.exe",
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
