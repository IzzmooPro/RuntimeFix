import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from installer import (  # noqa: E402
    InstallError,
    InstallResult,
    _build_msi_command,
    _install_directx_redist,
    _run_command,
    _run_install_attempts,
    _safe_extract_zip,
    install_component,
)


class InstallerTests(unittest.TestCase):
    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            archive = Path(directory) / "bad.zip"
            destination = Path(directory) / "extract"
            with zipfile.ZipFile(archive, "w") as file:
                file.writestr("../escaped.exe", b"bad")
            with self.assertRaises(InstallError):
                _safe_extract_zip(str(archive), str(destination))
            self.assertFalse((Path(directory) / "escaped.exe").exists())

    def test_safe_zip_is_extracted(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            archive = Path(directory) / "good.zip"
            destination = Path(directory) / "extract"
            with zipfile.ZipFile(archive, "w") as file:
                file.writestr("bin/setup.exe", b"ok")
            _safe_extract_zip(str(archive), str(destination))
            self.assertEqual((destination / "bin" / "setup.exe").read_bytes(), b"ok")

    def test_windows_tools_use_absolute_system32_path(self):
        command = _build_msi_command("package.msi", ["/qn"], "install.log")
        self.assertTrue(os.path.isabs(command[0]))
        self.assertTrue(command[0].lower().endswith(r"\system32\msiexec.exe"))

    def test_directx_stops_when_extraction_fails(self):
        failed = InstallResult("DirectX [extract]", 5, False)
        with patch("installer._run_command", return_value=failed) as run:
            result = _install_directx_redist("DirectX", "directx.exe")
        self.assertFalse(result.success)
        self.assertEqual(result.return_code, 5)
        run.assert_called_once()

    def test_standard_msi_uses_msiexec_and_log(self):
        component = {
            "name": "MSI Example",
            "silent_args": ["/qn"],
        }
        expected = InstallResult("MSI Example", 0, True)
        with patch("installer._run_command", return_value=expected) as run:
            result = install_component(component, "example.msi")
        self.assertIs(result, expected)
        command, name, log_path = run.call_args.args
        self.assertEqual(name, "MSI Example")
        self.assertTrue(command[0].lower().endswith(r"\system32\msiexec.exe"))
        self.assertIn("/L*v", command)
        self.assertTrue(log_path.endswith("_install.log"))

    def test_install_attempts_continue_until_success(self):
        failure = InstallResult("VC++", 1603, False)
        success = InstallResult("VC++", 0, True)
        attempts = [["setup.exe", "/first"], ["setup.exe", "/second"]]
        with patch(
            "installer._run_command",
            side_effect=[failure, success],
        ) as run:
            result = _run_install_attempts("VC++", attempts)
        self.assertTrue(result.success)
        self.assertEqual(run.call_count, 2)

    def test_run_command_maps_restart_and_already_installed_codes(self):
        for return_code, restart in ((3010, True), (1638, False)):
            completed = SimpleNamespace(
                returncode=return_code,
                stdout="",
                stderr="",
            )
            with (
                self.subTest(return_code=return_code),
                patch("installer.subprocess.run", return_value=completed),
            ):
                result = _run_command(["setup.exe"], "Example", "")
                self.assertTrue(result.success)
                self.assertEqual(result.restart_required, restart)


if __name__ == "__main__":
    unittest.main()
