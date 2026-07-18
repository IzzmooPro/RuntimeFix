import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from security import SecurityError, SecurityManager  # noqa: E402


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.security = SecurityManager(["example.com"])

    def test_url_validation(self):
        self.security.validate_url("https://example.com/file.exe")
        self.security.validate_url("https://cdn.example.com/file.exe")

        for url in (
            "http://example.com/file.exe",
            "https://example.com.evil.test/file.exe",
            "https://evil.test/file.exe",
        ):
            with self.subTest(url=url), self.assertRaises(SecurityError):
                self.security.validate_url(url)

    def test_sha256_validation(self):
        payload = b"RuntimeFix security test"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "file.exe"
            path.write_bytes(payload)
            self.security.verify_sha256(str(path), digest)
            with self.assertRaises(SecurityError):
                self.security.verify_sha256(str(path), "0" * 64)
            for invalid in ("", "abc", "g" * 64):
                with self.subTest(invalid=invalid), self.assertRaises(SecurityError):
                    self.security.verify_sha256(str(path), invalid)

    def test_invalid_domain_configuration_is_rejected(self):
        for domains in ([], ["https://example.com"], ["example.com/path"], [""]):
            with self.subTest(domains=domains), self.assertRaises(ValueError):
                SecurityManager(domains)

    def test_url_credentials_and_nonstandard_ports_are_rejected(self):
        for url in (
            "https://user@example.com/file.exe",
            "https://example.com:444/file.exe",
        ):
            with self.subTest(url=url), self.assertRaises(SecurityError):
                self.security.validate_url(url)

    def test_unreadable_file_is_reported_as_security_error(self):
        with self.assertRaises(SecurityError):
            self.security.verify_sha256(
                str(ROOT / "does-not-exist.exe"),
                "0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
