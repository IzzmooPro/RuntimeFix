import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from downloader import DownloadError, download_file  # noqa: E402


class _FakeResponse:
    def __init__(self, chunks, content_length, url="https://example.com/file.exe"):
        self._chunks = chunks
        self.headers = {"content-length": str(content_length)}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield from self._chunks


class _FakeSession:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, *_args, **_kwargs):
        return self.response


class DownloaderTests(unittest.TestCase):
    def test_content_length_mismatch_is_rejected(self):
        response = _FakeResponse([b"abc"], 4)
        with (
            tempfile.TemporaryDirectory(dir=ROOT) as directory,
            patch("downloader.CACHE_DIR", directory),
            patch(
                "downloader._build_session",
                return_value=_FakeSession(response),
            ),
        ):
            with self.assertRaises(DownloadError):
                download_file("https://example.com/file.exe")
            self.assertFalse(any(Path(directory).iterdir()))

    def test_final_url_is_always_validated_and_hint_is_sanitized(self):
        response = _FakeResponse([b"data"], 4)
        validated = []
        with (
            tempfile.TemporaryDirectory(dir=ROOT) as directory,
            patch("downloader.CACHE_DIR", directory),
            patch(
                "downloader._build_session",
                return_value=_FakeSession(response),
            ),
        ):
            path = download_file(
                "https://example.com/file.exe",
                filename_hint="../unsafe.exe",
                url_validator=validated.append,
            )
            self.assertEqual(validated, ["https://example.com/file.exe"])
            self.assertEqual(Path(path).parent, Path(directory))
            self.assertEqual(Path(path).name, "unsafe.exe")
            self.assertEqual(Path(path).read_bytes(), b"data")


if __name__ == "__main__":
    unittest.main()
