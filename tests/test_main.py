"""main.py giriş noktası — config yükleme davranışı."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

_spec = importlib.util.spec_from_file_location("runtimefix_main", ROOT / "main.py")
main_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main_module)


class ConfigLoadingTests(unittest.TestCase):
    def test_real_config_loads_with_components_and_domains(self):
        config = main_module.load_config()
        self.assertTrue(config["components"])
        self.assertTrue(config["allowed_domains"])

    def test_missing_config_fails_loudly_instead_of_starting_empty(self):
        """Config okunamazsa program bileşensiz açılmamalı, durmalı."""
        with patch.object(
            main_module, "LOCAL_CONFIG", str(ROOT / "does-not-exist.json")
        ):
            with self.assertRaises(SystemExit) as caught:
                main_module.load_config()
        self.assertIn("config.json", str(caught.exception))

    def test_corrupt_config_fails_loudly(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            broken = Path(directory) / "config.json"
            broken.write_text("{ bozuk json", encoding="utf-8")
            with patch.object(main_module, "LOCAL_CONFIG", str(broken)):
                with self.assertRaises(SystemExit):
                    main_module.load_config()

    def test_config_is_read_only_from_the_local_file(self):
        """Uzak config mekanizması bilerek kaldırıldı; ağ erişimi olmamalı."""
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            local = Path(directory) / "config.json"
            local.write_text(
                json.dumps({"components": [{"name": "X"}], "allowed_domains": ["a.test"]}),
                encoding="utf-8",
            )
            with patch.object(main_module, "LOCAL_CONFIG", str(local)):
                config = main_module.load_config()
        self.assertEqual(config["components"], [{"name": "X"}])


if __name__ == "__main__":
    unittest.main()
