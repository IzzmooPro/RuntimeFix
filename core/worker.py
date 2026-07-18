# -*- coding: utf-8 -*-
"""
worker.py - Background QThread worker for RuntimeFix
Orchestrates: download → SHA256 verify → install pipeline.
Emits human-friendly status messages.
"""

import logging
import os
from typing import List

from PyQt6.QtCore import QObject, pyqtSignal

from downloader import download_file, DownloadError, CACHE_DIR, resolve_filename_from_url, find_cached
from installer import install_component, InstallError, InstallResult
from security import SecurityManager, SecurityError

logger = logging.getLogger("RuntimeFix.worker")

# ── Human-friendly error translations ─────────────────────────────────────
_RC_MESSAGES = {
    1602: "The installation was cancelled before it could finish.",
    1603: "Installation failed. This often happens when another installer is running. Please close any open installers and try again.",
    1618: "Another installation is already in progress. Please wait for it to finish, then try again.",
    1619: "The installer file appears to be corrupted. Try deleting the downloads folder and running again.",
    1638: "A newer version of this component is already installed — no action needed.",
    1641: "Installation successful. A restart is needed to finish setting things up.",
    3010: "Installation successful. A restart is needed to finish setting things up.",
    5: "Access was denied. Make sure the program is running as Administrator.",
}

def _human_error(name: str, rc: int, log_path: str = "") -> str:
    base = _RC_MESSAGES.get(rc, f"Something went wrong while installing {name}. (Code {rc})")
    if log_path:
        base += f"\n\nA detailed log was saved to:\n{log_path}"
    return base


class WorkerSignals(QObject):
    progress               = pyqtSignal(int)          # 0-100 overall
    status                 = pyqtSignal(str)           # human-readable status
    file_download_progress = pyqtSignal(str, int, float)  # filename, %, MB/s
    component_error        = pyqtSignal(str, str)      # name, human detail
    component_success      = pyqtSignal(str)           # name → mark green
    restart_required       = pyqtSignal()
    finished               = pyqtSignal(bool)          # True = no critical errors


class DownloadInstallWorker(QObject):
    def __init__(self, components: List[dict], security_manager: SecurityManager) -> None:
        super().__init__()
        self.components     = components
        self.security       = security_manager
        self.signals        = WorkerSignals()
        self._cancelled     = False
        self._had_error     = False
        self._restart_needed = False

    @property
    def is_cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True
        self.signals.status.emit("Cancelling… please wait.")
        logger.info("Cancellation requested.")

    def run(self):
        total = len(self.components)
        if total == 0:
            self.signals.finished.emit(True)
            return

        downloaded = []

        try:
            # ── Phase 1 – Downloads (0-50 %) ─────────────────────────────
            for idx, comp in enumerate(self.components):
                if self._cancelled:
                    break

                name         = comp.get("name", f"Component {idx+1}")
                url          = comp.get("url", "")
                install_type = comp.get("install_type", "")
                base_pct     = int((idx / total) * 50)

                # DISM bileşenleri indirme gerektirmez — doğrudan kurulum kuyruğuna al
                if install_type == "dism_feature":
                    self.signals.status.emit(f"{name} Windows özelliği olarak etkinleştirilecek…")
                    downloaded.append({"component": comp, "path": ""})
                    self.signals.progress.emit(base_pct + int(50 / total))
                    continue

                # Security gate
                try:
                    self.security.validate_url(url)
                except SecurityError as exc:
                    self._emit_error(name, f"This download was blocked for security reasons:\n{exc}")
                    continue

                # Check cache first (case-insensitive — sunucu büyük .EXE dönebilir)
                _hint    = comp.get("filename_hint")
                _fname   = _hint or resolve_filename_from_url(url)
                _cached  = find_cached(CACHE_DIR, _fname)
                if _cached:
                    self.signals.status.emit(f"Using cached file for {name}…")
                else:
                    self.signals.status.emit(f"Downloading {name}…")

                def _prog(filename, pct, speed, _base=base_pct, _total=total):
                    self.signals.file_download_progress.emit(filename, pct, speed)
                    overall = _base + int((pct / 100) * (50 / _total))
                    self.signals.progress.emit(overall)

                try:
                    file_path = download_file(
                        url, "",
                        progress_cb=_prog,
                        cancel_check=lambda: self._cancelled,
                        filename_hint=comp.get("filename_hint"),
                        url_validator=self.security.validate_url,
                    )
                except DownloadError as exc:
                    if self._cancelled:
                        break
                    self._emit_error(
                        name,
                        f"We couldn't download {name}. Please check your internet connection and try again.\n\nDetails: {exc}"
                    )
                    continue
                except SecurityError as exc:
                    self._emit_error(
                        name,
                        f"The download for {name} was redirected to an untrusted address and was blocked:\n{exc}"
                    )
                    continue

                # SHA-256 verification
                try:
                    self.security.verify_sha256(file_path, comp.get("sha256", ""))
                except SecurityError as exc:
                    self._emit_error(name, self._sha_mismatch_message(comp, name, exc))
                    os.remove(file_path)
                    continue

                downloaded.append({"component": comp, "path": file_path})
                self.signals.progress.emit(base_pct + int(50 / total))

            if self._cancelled:
                return

            # ── Phase 2 – Installations (50-100 %) ───────────────────────
            to_install = len(downloaded)
            for inst_idx, entry in enumerate(downloaded):
                if self._cancelled:
                    break

                comp     = entry["component"]
                path     = entry["path"]
                name     = comp.get("name", path)
                base_pct = 50 + int((inst_idx / max(to_install, 1)) * 50)

                self.signals.progress.emit(base_pct)
                self.signals.status.emit(f"Installing {name}…")

                # Kurulumdan hemen önce hash'i yeniden doğrula: indirme ile kurulum
                # arasında dosya değişmiş/bozulmuş olabilir (doğrulanan dosya ≠
                # kurulan dosya durumunu engeller).
                if path:
                    try:
                        self.security.verify_sha256(path, comp.get("sha256", ""))
                    except SecurityError as exc:
                        self._emit_error(name, self._sha_mismatch_message(comp, name, exc))
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        continue

                try:
                    result: InstallResult = install_component(comp, path)
                except InstallError as exc:
                    self._emit_error(name, f"Could not install {name}.\n\n{exc}")
                    continue

                if result.skipped:
                    self.signals.status.emit(f"{name} — skipped (cannot install automatically).")
                    logger.info(f"Skipped: {name}")
                elif result.success:
                    if result.restart_required:
                        self._restart_needed = True
                    self.signals.status.emit(f"{name} installed successfully.")
                    logger.info(f"Install OK: {name} rc={result.return_code}")
                    self.signals.component_success.emit(name)
                else:
                    logger.error(f"Install FAILED: {name} rc={result.return_code} log={result.log_path!r}")
                    human_msg = _human_error(name, result.return_code, result.log_path)
                    self._emit_error(name, human_msg)

                overall = 50 + int(((inst_idx + 1) / max(to_install, 1)) * 50)
                self.signals.progress.emit(overall)

                # NOT: İndirilen dosya bilinçli olarak SİLİNMİYOR — downloads/
                # klasörü offline cache görevi görür (README'deki "tekrar
                # indirilmez" vaadi). Cache'i temizlemek isteyen kullanıcı
                # klasörü elle silebilir.

        except Exception as exc:
            logger.exception("Unexpected worker error")
            self._emit_error("Installer", str(exc))
            self._had_error = True

        finally:
            self.signals.progress.emit(100)
            if self._restart_needed and not self._cancelled:
                self.signals.restart_required.emit()
            self.signals.finished.emit(not self._had_error and not self._cancelled)

    @staticmethod
    def _sha_mismatch_message(comp: dict, name: str, exc: Exception) -> str:
        """SHA-256 uyuşmazlığı için kullanıcı dostu mesaj üretir.

        'evergreen' işaretli bileşenlerin URL'leri (aka.ms, fwlink, oracle
        /latest/) sürekli en yeni sürüme işaret eder; yayıncı yeni sürüm
        çıkardığında hash doğal olarak değişir — bu bir saldırı değildir.
        """
        if comp.get("evergreen"):
            return (
                f"The file for {name} doesn't match the expected checksum. "
                f"This component is downloaded from an always-latest URL, so the "
                f"publisher has most likely released a new version. "
                f"Update the sha256 value in data/config.json (debug/hash_updater.py "
                f"can do this automatically) and try again.\n\nDetails: {exc}"
            )
        return (
            f"The downloaded file for {name} failed a security check and was removed. "
            f"Please try again — if the problem persists, contact support.\n\nDetails: {exc}"
        )

    def _emit_error(self, name: str, detail: str):
        self._had_error = True
        logger.error(f"[{name}] {detail}")
        self.signals.component_error.emit(name, detail)
