import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from utils import (  # noqa: E402
    detect_file_exists,
    detect_java,
    is_component_installed,
    sanitize_filename,
)


class UtilsTests(unittest.TestCase):
    def test_filename_sanitization_blocks_path_components(self):
        self.assertEqual(sanitize_filename("../bad:name.exe"), "badname.exe")
        self.assertEqual(sanitize_filename("..."), "download.tmp")

    def test_file_detection(self):
        with tempfile.NamedTemporaryFile(dir=ROOT) as file:
            self.assertTrue(detect_file_exists(file.name))
        self.assertFalse(detect_file_exists(str(ROOT / "missing.file")))

    def test_java_rejects_unknown_architecture(self):
        self.assertFalse(detect_java("arm64"))

    def test_detection_dispatches_config_values(self):
        cases = [
            ("dotnet", "8.0", "detect_dotnet_sdk", ("8.0",)),
            (
                "dotnet_desktop",
                "8.0:x86:aspnet",
                "detect_dotnet_desktop",
                ("8.0", "x86", "aspnet"),
            ),
            ("vcredist", "2015:x64", "detect_vcredist", ("2015", "x64")),
            ("registry", "HKLM\\Example", "detect_registry_key", ("HKLM\\Example",)),
            ("java", "x86", "detect_java", ("x86",)),
            ("file", "C:\\example.dll", "detect_file_exists", ("C:\\example.dll",)),
            ("dotnet_framework", "533320", "detect_dotnet_framework", (533320,)),
            ("jdk", "21", "detect_jdk_version", ("21",)),
        ]
        for detect_type, value, target, expected_args in cases:
            with (
                self.subTest(detect_type=detect_type),
                patch(f"utils.{target}", return_value=True) as detector,
            ):
                self.assertTrue(
                    is_component_installed(
                        {
                            "detect_type": detect_type,
                            "detect_value": value,
                        }
                    )
                )
                detector.assert_called_once_with(*expected_args)

    def test_unknown_detection_type_is_not_assumed_installed(self):
        self.assertFalse(
            is_component_installed(
                {"detect_type": "unknown", "detect_value": ""}
            )
        )


if __name__ == "__main__":
    unittest.main()
