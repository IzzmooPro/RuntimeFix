"""Config sapma denetleyicisinin kendi testleri (.github/scripts)."""

import importlib.util
import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check_config_drift.py"

_spec = importlib.util.spec_from_file_location("check_config_drift", SCRIPT)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


class _FakeResponse:
    def __init__(self, payload=b"", url="https://example.com/file.exe", status=200):
        self._stream = io.BytesIO(payload)
        self._url = url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self._stream.read(size)

    def geturl(self):
        return self._url


class RequestTests(unittest.TestCase):
    def test_oracle_urls_carry_the_license_cookie(self):
        request = drift._request("https://javadl.oracle.com/webapps/download/AutoDL")
        self.assertIn("oraclelicense", request.headers.get("Cookie", ""))

    def test_other_urls_do_not_carry_cookies(self):
        request = drift._request("https://download.microsoft.com/file.exe")
        self.assertIsNone(request.headers.get("Cookie"))

    def test_reachability_only_reads_the_first_byte(self):
        response = _FakeResponse(payload=b"x" * 5000)
        with patch("urllib.request.urlopen", return_value=response):
            ok, note = drift.check_reachable("https://example.com/big.exe")
        self.assertTrue(ok)
        self.assertIn("HTTP", note)
        # 1 bayt okundu, geri kalanı akışta duruyor: dosya indirilmedi
        self.assertEqual(len(response._stream.read()), 4999)

    def test_redirect_target_is_reported(self):
        response = _FakeResponse(url="https://cdn.other.test/file.exe")
        with patch("urllib.request.urlopen", return_value=response):
            _ok, note = drift.check_reachable("https://aka.ms/x")
        self.assertIn("cdn.other.test", note)

    def test_http_error_is_a_failure(self):
        error = urllib.error.HTTPError(
            "https://example.com/gone.exe", 404, "Not Found", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=error):
            ok, note = drift.check_reachable("https://example.com/gone.exe")
        self.assertFalse(ok)
        self.assertIn("404", note)


class ExitCodeTests(unittest.TestCase):
    """Sapma varsa CI kırılmalı — sessizce geçmemeli."""

    def _run_main(self, argv, urlopen):
        with (
            patch.object(sys, "argv", ["check_config_drift.py", *argv]),
            patch("urllib.request.urlopen", side_effect=urlopen),
            patch("sys.stdout", new=io.StringIO()) as output,
        ):
            code = drift.main()
        return code, output.getvalue()

    def test_all_reachable_returns_success(self):
        code, output = self._run_main([], lambda *a, **k: _FakeResponse(b"x"))
        self.assertEqual(code, 0)
        self.assertIn("Sapma yok", output)

    def test_unreachable_url_fails_the_run(self):
        error = urllib.error.HTTPError("https://x/y", 404, "gone", {}, None)
        code, output = self._run_main([], error)
        self.assertEqual(code, 1)
        self.assertIn("Erişilemeyen adresler", output)

    def test_evergreen_hash_drift_fails_the_run(self):
        """Yayıncı yeni sürüm yayınladığında bakımcı haberdar olmalı."""

        def urlopen(request, *_args, **_kwargs):
            # Erişilebilirlik isteğinde Range başlığı var, indirmede yok
            headers = getattr(request, "headers", {})
            if any(key.lower() == "range" for key in headers):
                return _FakeResponse(b"x")
            return _FakeResponse(b"config'dekinden farkli icerik")

        code, output = self._run_main(["--hash", "evergreen"], urlopen)
        self.assertEqual(code, 1)
        self.assertIn("Hash'i değişen bileşenler", output)


if __name__ == "__main__":
    unittest.main()
