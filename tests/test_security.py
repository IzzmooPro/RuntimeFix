import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from security import (  # noqa: E402
    SecurityError,
    SecurityManager,
    authenticode_signer,
)


# Gerçek Get-AuthenticodeSignature çıktısından alınmış subject dizeleri
ORACLE_SUBJECT = (
    'CN="Oracle America, Inc.", O="Oracle America, Inc.", '
    "L=Redwood City, S=California, C=US"
)
MICROSOFT_SUBJECT = (
    "CN=Microsoft Corporation, O=Microsoft Corporation, "
    "L=Redmond, S=Washington, C=US"
)


@contextmanager
def fake_signature(status="Valid", subject=MICROSOFT_SUBJECT):
    """PowerShell imza sorgusunun çıktısını taklit eder."""
    lines = [f"STATUS={status}"]
    if subject is not None:
        lines.append(f"SUBJECT={subject}")
    completed = SimpleNamespace(
        returncode=0, stdout="\n".join(lines) + "\n", stderr=""
    )
    with patch("security.run_hidden", return_value=completed) as run:
        yield run


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


class AuthenticodeTests(unittest.TestCase):
    """İmza okuma katmanı — CN ayrıştırma ve güvenli çağrı biçimi."""

    def test_quoted_cn_with_comma_is_parsed(self):
        # Oracle'ın CN'i virgül içerir ve tırnaklanır: naif split ile bölünürdü
        with fake_signature(subject=ORACLE_SUBJECT):
            self.assertEqual(
                authenticode_signer("setup.exe"), "Oracle America, Inc."
            )

    def test_plain_cn_is_parsed(self):
        with fake_signature(subject=MICROSOFT_SUBJECT):
            self.assertEqual(
                authenticode_signer("setup.exe"), "Microsoft Corporation"
            )

    def test_invalid_status_yields_no_signer(self):
        for status in ("NotSigned", "HashMismatch", "UnknownError"):
            with self.subTest(status=status), fake_signature(status=status):
                self.assertIsNone(authenticode_signer("setup.exe"))

    def test_missing_subject_yields_no_signer(self):
        with fake_signature(subject=None):
            self.assertIsNone(authenticode_signer("setup.exe"))

    def test_query_failure_yields_no_signer(self):
        with patch("security.run_hidden", side_effect=OSError("boom")):
            self.assertIsNone(authenticode_signer("setup.exe"))

    def test_file_path_never_reaches_the_command_line(self):
        """Yol komut satırına gömülseydi tırnak/kaçış enjeksiyonu mümkün olurdu."""
        hostile = 'C:\\tmp\\a"; Remove-Item C:\\ -Recurse; "b.exe'
        with fake_signature() as run:
            authenticode_signer(hostile)
        command, = run.call_args.args
        self.assertNotIn(hostile, " ".join(command))
        environment = run.call_args.kwargs["env"]
        self.assertEqual(
            environment["RUNTIMEFIX_VERIFY_PATH"], os.path.abspath(hostile)
        )

    @unittest.skipUnless(os.name == "nt", "Authenticode yalnızca Windows'ta")
    def test_reads_signature_of_a_real_signed_binary(self):
        """
        Taklit değil: gerçekten imzalı bir dosyadan yayıncı adı okunur.

        Hangi dosyanın *gömülü* imzası olduğu ortama göre değişir — CI
        imajlarında sistem dosyaları çoğu zaman yalnızca katalog imzalıdır ve
        Get-AuthenticodeSignature onları "Valid" saymaz. Bu yüzden birkaç aday
        denenir, hiçbiri doğrulanamıyorsa test atlanır. Ürün kodunun "emin
        olamadığında None döndür" davranışı ayrıca test ediliyor.
        """
        system32 = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "System32"
        )
        candidates = [
            os.path.join(system32, "notepad.exe"),
            os.path.join(system32, "WindowsPowerShell", "v1.0", "powershell.exe"),
            sys.executable,
        ]
        for path in candidates:
            if not os.path.isfile(path):
                continue
            signer = authenticode_signer(path)
            if signer:
                # Ham subject değil, yalnızca CN değeri dönmeli.
                # (Virgül serbest: "Oracle America, Inc." geçerli bir CN'dir.)
                self.assertNotIn("CN=", signer)
                self.assertNotIn("O=", signer)
                return
        self.skipTest("bu ortamda gömülü Authenticode imzalı aday dosya yok")

    @unittest.skipUnless(os.name == "nt", "Authenticode yalnızca Windows'ta")
    def test_unsigned_file_is_reported_as_unverified(self):
        """Gerçek imzasız dosya — imza doğrulaması bunu kabul etmemeli."""
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "unsigned.exe"
            path.write_bytes(b"MZ not really a signed binary")
            self.assertIsNone(authenticode_signer(str(path)))


class EvergreenVerificationTests(unittest.TestCase):
    """Yayıncı yeni sürüm çıkardığında hash'in kaçınılmaz olarak değişmesi."""

    def setUp(self):
        self.security = SecurityManager(["example.com"])
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "vc_redist.x64.exe"
        self.path.write_bytes(b"yeni surum icerigi")
        self.correct_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.stale_hash = "0" * 64

    def component(self, **overrides):
        component = {
            "name": "VC++ Redist 2015-2022 (x64)",
            "sha256": self.stale_hash,
            "evergreen": True,
            "publisher": "Microsoft Corporation",
        }
        component.update(overrides)
        return component

    def test_matching_hash_wins_without_touching_signatures(self):
        with patch("security.authenticode_signer") as signer:
            result = self.security.verify_download(
                str(self.path), self.component(sha256=self.correct_hash)
            )
        self.assertEqual(result, "sha256")
        signer.assert_not_called()

    def test_new_publisher_release_is_accepted_via_signature(self):
        """Eski davranış: burada kurulum kırılıyordu."""
        with patch(
            "security.authenticode_signer", return_value="Microsoft Corporation"
        ):
            result = self.security.verify_download(
                str(self.path), self.component()
            )
        self.assertEqual(result, "signature")

    def test_publisher_name_comparison_ignores_case(self):
        with patch(
            "security.authenticode_signer", return_value="microsoft corporation"
        ):
            self.assertEqual(
                self.security.verify_download(str(self.path), self.component()),
                "signature",
            )

    def test_file_signed_by_someone_else_is_rejected(self):
        with patch("security.authenticode_signer", return_value="Evil Corp"):
            with self.assertRaises(SecurityError) as caught:
                self.security.verify_download(str(self.path), self.component())
        self.assertIn("Evil Corp", str(caught.exception))

    def test_unsigned_file_is_rejected(self):
        with patch("security.authenticode_signer", return_value=None):
            with self.assertRaises(SecurityError):
                self.security.verify_download(str(self.path), self.component())

    def test_signature_fallback_never_applies_to_normal_components(self):
        """Sabit URL'li bileşende hash uyuşmazlığı, dosya imzalı olsa da hatadır."""
        with patch(
            "security.authenticode_signer", return_value="Microsoft Corporation"
        ) as signer:
            with self.assertRaises(SecurityError):
                self.security.verify_download(
                    str(self.path), self.component(evergreen=False)
                )
        signer.assert_not_called()

    def test_evergreen_without_publisher_still_requires_hash(self):
        component = self.component()
        component.pop("publisher")
        with patch("security.authenticode_signer") as signer:
            with self.assertRaises(SecurityError):
                self.security.verify_download(str(self.path), component)
        signer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
