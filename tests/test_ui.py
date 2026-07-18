import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from security import SecurityManager  # noqa: E402
from ui import (  # noqa: E402
    MainWindow,
    UpdateDownloader,
    configure_application,
    create_question_dialog,
    estimate_size_mb,
)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_application(cls.app)

    def setUp(self):
        with patch("ui.QTimer.singleShot") as timer:
            self.window = MainWindow([], SecurityManager(), "3.0.0")
        delays = [call.args[0] for call in timer.call_args_list]
        self.assertIn(250, delays)
        self.assertIn(400, delays)

    def tearDown(self):
        self.window.close()

    def test_application_uses_dark_dialog_theme(self):
        stylesheet = self.app.styleSheet()
        self.assertIn("QMessageBox", stylesheet)
        self.assertIn("background-color: #17181c", stylesheet)
        self.assertIn("QMessageBox QPushButton:default", stylesheet)

    def test_specific_size_rule_wins_over_generic_rule(self):
        self.assertEqual(
            estimate_size_mb({"name": "XNA Framework Redistributable 3.1"}),
            7,
        )

    def test_question_dialog_uses_localized_buttons(self):
        dialog, yes_button = create_question_dialog(
            None,
            "Güncelleme",
            "Yeni sürüm mevcut.",
            "tr",
        )
        button_texts = {button.text() for button in dialog.buttons()}
        self.assertEqual(yes_button.text(), "Evet")
        self.assertEqual(button_texts, {"Evet", "Hayır"})
        dialog.close()

    def test_startup_update_prompts_once_and_keeps_banner_on_no(self):
        self.window._update_check_mode = "startup"
        info = {
            "available": True,
            "version": "3.0.1",
            "download_url": "https://example.com/RuntimeFix-Setup-3.0.1.exe",
        }
        with (
            patch("ui.QTimer.singleShot"),
            patch("ui.ask_question", return_value=False) as question,
        ):
            self.window._on_update_result(info)

        question.assert_called_once()
        self.assertFalse(self.window._update_bar.isHidden())
        self.assertEqual(self.window._update_check_mode, "silent")

    def test_verified_update_starts_setup_without_second_prompt(self):
        setup_path = str(ROOT / "RuntimeFix-Setup-3.0.1.exe")
        with (
            patch("ui.QTimer.singleShot") as timer,
            patch("ui.ask_question") as question,
            patch("ui.subprocess.Popen") as popen,
        ):
            self.window._on_update_downloaded(setup_path)

        question.assert_not_called()
        popen.assert_called_once_with([setup_path], cwd=str(ROOT))
        self.assertGreaterEqual(timer.call_count, 1)

    def test_update_downloader_passes_cancellation_callback(self):
        downloader = UpdateDownloader({"version": "3.0.1"}, str(ROOT))
        downloader.cancel()
        with patch(
            "ui.download_update",
            return_value=str(ROOT / "setup.exe"),
        ) as download:
            downloader.run()
        cancel_check = download.call_args.kwargs["cancel_check"]
        self.assertTrue(cancel_check())

    def test_update_setup_waits_for_other_background_threads(self):
        setup_path = str(ROOT / "RuntimeFix-Setup-3.0.1.exe")
        scan_thread = MagicMock()
        scan_thread.isRunning.return_value = True
        self.window._scan_thread = scan_thread
        with (
            patch("ui.subprocess.Popen") as popen,
            patch("ui.QTimer.singleShot"),
        ):
            self.window._on_update_downloaded(setup_path)
            popen.assert_not_called()

            scan_thread.isRunning.return_value = False
            self.window._cleanup_scan_thread()
            popen.assert_called_once_with([setup_path], cwd=str(ROOT))

    def test_close_waits_for_background_scan_thread(self):
        thread = MagicMock()
        thread.isRunning.return_value = True
        event = MagicMock()
        self.window._scan_thread = thread

        self.window.closeEvent(event)

        event.ignore.assert_called_once()
        self.assertTrue(self.window._close_pending)
        self.assertFalse(self.window.isEnabled())

        thread.isRunning.return_value = False
        with patch("ui.QTimer.singleShot") as timer:
            self.window._cleanup_scan_thread()
        timer.assert_called_once_with(0, self.window.close)


if __name__ == "__main__":
    unittest.main()
