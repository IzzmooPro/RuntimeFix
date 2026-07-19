import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from languages import get as T  # noqa: E402
from security import SecurityManager  # noqa: E402
from ui import (  # noqa: E402
    MainWindow,
    ScanWorker,
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
            self.window = MainWindow([], SecurityManager(), "3.00")
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

    def test_version_text_preserves_two_digits(self):
        labels = {label.text() for label in self.window.findChildren(QLabel)}
        self.assertIn("v3.00", labels)
        self.assertNotIn("v3.0", labels)

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

    UPDATE_INFO = {
        "available": True,
        "version": "3.05",
        "download_url": "https://example.com/RuntimeFix-Setup-3.05.exe",
    }

    def test_startup_shows_banner_without_opening_a_dialog(self):
        """Açılışta kullanıcının önüne soru penceresi çıkmamalı."""
        self.window._update_check_mode = "silent"
        with (
            patch("ui.QTimer.singleShot"),
            patch("ui.ask_question", return_value=False) as question,
        ):
            self.window._on_update_result(self.UPDATE_INFO)

        question.assert_not_called()
        self.assertFalse(self.window._update_bar.isHidden())
        self.assertEqual(self.window._update_check_mode, "silent")

    def test_manual_check_still_opens_update_dialog(self):
        self.window._update_check_mode = "manual"
        with (
            patch("ui.QTimer.singleShot"),
            patch("ui.ask_question", return_value=False) as question,
        ):
            self.window._on_update_result(self.UPDATE_INFO)

        question.assert_called_once()
        self.assertFalse(self.window._update_bar.isHidden())

    def test_banner_button_starts_update_on_user_click(self):
        """Şerit kullanıcı tıklamasıyla güncelleme akışını başlatabilmeli."""
        self.window._update_info = dict(self.UPDATE_INFO)
        with (
            patch("ui.QTimer.singleShot"),
            patch("ui.ask_question", return_value=False) as question,
        ):
            self.window._update_btn.click()
        question.assert_called_once()

    def test_startup_check_mode_is_silent(self):
        with patch.object(MainWindow, "_check_updates") as check:
            with patch("ui.QTimer.singleShot") as timer:
                window = MainWindow([], SecurityManager(), "3.00")
            update_callbacks = [
                call.args[1] for call in timer.call_args_list if call.args[0] == 250
            ]
            self.assertEqual(len(update_callbacks), 1)
            update_callbacks[0]()
        check.assert_called_once_with("silent")
        window.close()

    def test_verified_update_starts_setup_without_second_prompt(self):
        setup_path = str(ROOT / "RuntimeFix-Setup-3.05.exe")
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
        downloader = UpdateDownloader({"version": "3.05"}, str(ROOT))
        downloader.cancel()
        with patch(
            "ui.download_update",
            return_value=str(ROOT / "setup.exe"),
        ) as download:
            downloader.run()
        cancel_check = download.call_args.kwargs["cancel_check"]
        self.assertTrue(cancel_check())

    def test_update_setup_waits_for_other_background_threads(self):
        setup_path = str(ROOT / "RuntimeFix-Setup-3.05.exe")
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

    def test_repair_reinstall_does_not_inflate_installed_count(self):
        components = [
            {"name": "Already Installed", "detect_type": "none"},
            {"name": "Missing One", "detect_type": "none"},
        ]
        window = self.window
        window._components = components
        with patch("ui.QTimer.singleShot"):
            window._on_scan_done([(components[0], True), (components[1], False)])
        self.assertEqual((window._ok_count, window._miss_count), (1, 1))

        # Onarım modu: zaten kurulu bileşen yeniden kurulur — sayaç değişmemeli
        window._on_component_success("Already Installed")
        self.assertEqual((window._ok_count, window._miss_count), (1, 1))

        # Gerçekten eksik olan bileşen kurulunca sayaçlar ilerler
        window._on_component_success("Missing One")
        self.assertEqual((window._ok_count, window._miss_count), (2, 0))

    def test_close_during_scan_cancels_it_and_shows_feedback(self):
        """
        X'e basıldıktan sonra pencere arka plan işi bitene kadar açık kalıyor.
        Geri bildirim olmadan bu donmuş pencere gibi görünüyordu; tarama da
        gereksiz yere sonuna kadar çalışıyordu.
        """
        thread = MagicMock()
        thread.isRunning.return_value = True
        scan_worker = MagicMock()
        self.window._scan_thread = thread
        self.window._scan_worker = scan_worker

        self.window.closeEvent(MagicMock())

        scan_worker.cancel.assert_called_once()
        self.assertEqual(self.window._headline.text(), T("tr", "closing"))

    def test_scan_worker_stops_early_when_cancelled(self):
        components = [{"name": f"C{i}", "detect_type": "none"} for i in range(20)]
        worker = ScanWorker(components)
        seen = []

        def fake_detect(component):
            seen.append(component["name"])
            if len(seen) == 3:
                worker.cancel()
            return False

        results = []
        worker.signals.done.connect(results.append)
        with patch("ui.is_component_installed", side_effect=fake_detect):
            worker.run()

        self.assertEqual(len(seen), 3)          # 20 değil, 3'te durdu
        self.assertEqual(len(results[0]), 3)    # kısmi sonuç yine de bildirildi

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
