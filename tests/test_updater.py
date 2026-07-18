import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from updater import _digest_matches, _safe_filename, is_newer_version


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(is_newer_version("2.4", "2.3"))
        self.assertTrue(is_newer_version("v2.3.1", "2.3"))
        self.assertFalse(is_newer_version("2.3", "2.3.0"))
        self.assertFalse(is_newer_version("2.2", "2.3"))

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
            _safe_filename('RuntimeFix:Setup/2.4?.exe'),
            "RuntimeFix_Setup_2.4_.exe",
        )


if __name__ == "__main__":
    unittest.main()
