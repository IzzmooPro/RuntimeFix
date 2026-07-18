import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from security import SecurityManager  # noqa: E402


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(
            (ROOT / "data" / "config.json").read_text(encoding="utf-8")
        )

    def test_component_names_are_unique(self):
        components = self.config["components"]
        names = [component["name"] for component in components]
        self.assertTrue(names)
        self.assertEqual(len(names), len(set(names)))

    def test_downloads_use_https_whitelist_and_sha256(self):
        security = SecurityManager(self.config["allowed_domains"])
        for component in self.config["components"]:
            url = component.get("url")
            if not url:
                self.assertEqual(component.get("install_type"), "dism_feature")
                continue

            with self.subTest(component=component["name"]):
                security.validate_url(url)
                self.assertRegex(
                    component.get("sha256", ""),
                    re.compile(r"^[0-9a-f]{64}$"),
                )

    def test_component_schema_and_cache_names_are_safe(self):
        filename_hints = []
        allowed_detect_types = {
            "dotnet",
            "dotnet_desktop",
            "vcredist",
            "registry",
            "webview2",
            "java",
            "msxml4",
            "file",
            "dotnet_framework",
            "dotnet_framework35",
            "jdk",
        }
        for component in self.config["components"]:
            with self.subTest(component=component["name"]):
                self.assertIsInstance(component.get("silent_args"), list)
                self.assertIn(component.get("detect_type"), allowed_detect_types)
                self.assertIn("detect_value", component)
                if component.get("filename_hint"):
                    self.assertRegex(
                        component["filename_hint"],
                        re.compile(r"^[A-Za-z0-9_.-]+$"),
                    )
                    filename_hints.append(component["filename_hint"].lower())
                if component.get("install_type") == "dism_feature":
                    self.assertTrue(component.get("dism_feature"))
                    self.assertFalse(component.get("url"))
        self.assertEqual(len(filename_hints), len(set(filename_hints)))

    def test_java_detection_distinguishes_architecture(self):
        java = {
            component["name"]: component["detect_value"]
            for component in self.config["components"]
            if component["name"].startswith("Java 8 Runtime")
        }
        self.assertEqual(java["Java 8 Runtime (JRE) (x86)"], "x86")
        self.assertEqual(java["Java 8 Runtime (JRE) (x64)"], "x64")

    def test_dotnet_urls_match_component_major_version(self):
        for component in self.config["components"]:
            if ".NET" not in component["name"] or not component.get("url"):
                continue
            match = re.search(r"(?:Runtime|SDK) (\d+)\.0", component["name"])
            if not match:
                continue
            with self.subTest(component=component["name"]):
                self.assertRegex(
                    component["url"],
                    re.compile(rf"(?:/|-){match.group(1)}\.0\."),
                )


if __name__ == "__main__":
    unittest.main()
