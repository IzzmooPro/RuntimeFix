import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from security import SecurityManager


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


if __name__ == "__main__":
    unittest.main()
