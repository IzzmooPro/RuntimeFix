# -*- coding: utf-8 -*-
"""
main.py - Application entry point for RuntimeFix
"""

import json
import logging
import os
import platform
import sys
import traceback

# core/ klasörünü Python modül yoluna ekle
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT_DIR, "core"))

from PyQt6.QtWidgets import QApplication, QMessageBox

from security import SecurityManager
from ui import MainWindow
from utils import is_admin, relaunch_as_admin, setup_logging
from app_info import APP_VERSION

logger = setup_logging()

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
LOCAL_CONFIG = os.path.join(BASE_DIR, "data", "config.json")


def _load_local_config() -> dict:
    with open(LOCAL_CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def load_config() -> dict:
    # Config yalnızca yerel dosyadan okunur. (Eski "uzak config güncelleme"
    # mekanizması kaldırıldı: imzasız uzak config, allowed_domains ve sha256
    # değerlerini değiştirebildiği için güvenlik riskiydi ve kullanılmıyordu.)
    try:
        return _load_local_config()
    except Exception as exc:
        logger.critical(f"Cannot load data/config.json: {exc}")
        raise SystemExit(f"Cannot load data/config.json:\n{exc}") from exc


def main() -> None:
    logger.info("=" * 60)
    logger.info(f"  RuntimeFix v{APP_VERSION} — Geliştirici Modu")
    logger.info(f"  Python: {platform.python_version()} | Platform: {platform.system()} {platform.release()}")
    logger.info("=" * 60)
    logger.info("Program başlatılıyor...")

    app = QApplication(sys.argv)
    app.setApplicationName("RuntimeFix")
    app.setApplicationVersion(APP_VERSION)

    # Admin check
    if platform.system() == "Windows":
        if not is_admin():
            logger.info("Yönetici yetkisi yok — UAC yükseltmesi isteniyor...")
            if relaunch_as_admin():
                sys.exit(0)
            else:
                QMessageBox.critical(
                    None, "Administrator Required",
                    "This program must be run as administrator.\n"
                    "Right-click → Run as administrator."
                )
                sys.exit(1)

    logger.info("✔ Yönetici yetkileriyle çalışıyor.")

    # Load config
    try:
        config = load_config()
    except SystemExit as exc:
        QMessageBox.critical(None, "Configuration Error", str(exc))
        sys.exit(1)

    components      = config.get("components", [])
    allowed_domains = config.get("allowed_domains", [])

    logger.info(f"✔ data/config.json yüklendi — {len(components)} bileşen tanımlı")
    logger.info(f"  İzin verilen domainler: {', '.join(allowed_domains[:5])}{'...' if len(allowed_domains) > 5 else ''}")

    if not components:
        QMessageBox.warning(None, "Empty Config",
            "data/config.json contains no components.")
        sys.exit(0)

    security = SecurityManager(allowed_domains if allowed_domains else None)

    logger.info("✔ Ana pencere oluşturuluyor...")
    window = MainWindow(components, security, APP_VERSION)
    window.show()
    logger.info("✔ Program hazır — kullanıcı etkileşimi bekleniyor")
    logger.info("-" * 60)

    exit_code = app.exec()
    logger.info(f"Program kapatıldı (exit code={exit_code})")
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        logger.critical(f"Unhandled exception:\n{tb}")
        summary = tb.strip().splitlines()[-1] if tb.strip() else "Bilinmeyen hata"
        try:
            error_app = QApplication.instance() or QApplication([])
            QMessageBox.critical(
                None,
                "RuntimeFix — Beklenmeyen Hata",
                "Program beklenmeyen bir hatayla kapandı.\n\n"
                f"{summary}\n\n"
                "Teknik ayrıntılar RuntimeFix log dosyasına kaydedildi.",
            )
        except Exception:
            try:
                print(f"RuntimeFix beklenmeyen hata:\n{tb}", file=sys.stderr)
            except Exception:
                pass
        sys.exit(1)
