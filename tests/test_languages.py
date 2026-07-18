import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from languages import LANGUAGES  # noqa: E402


class LanguageTests(unittest.TestCase):
    def test_all_languages_have_the_same_keys(self):
        reference = set(LANGUAGES["tr"])
        for code, translations in LANGUAGES.items():
            with self.subTest(language=code):
                self.assertEqual(set(translations), reference)

    def test_trust_text_does_not_claim_microsoft_only(self):
        for code, translations in LANGUAGES.items():
            with self.subTest(language=code):
                first_line = translations["trust_line"].splitlines()[0].lower()
                self.assertNotIn("microsoft", first_line)


if __name__ == "__main__":
    unittest.main()
