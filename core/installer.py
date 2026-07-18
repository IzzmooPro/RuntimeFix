# -*- coding: utf-8 -*-
"""
installer.py - Silent install engine for RuntimeFix.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

logger = logging.getLogger("RuntimeFix.installer")

RC_SUCCESS = 0
RC_RESTART_REQUIRED = 3010
INSTALL_TIMEOUT = 900

# Bazı installer'ların "başarılı" veya "zaten yüklü" döndürdüğü ek kodlar
RC_EXTRA_SUCCESS = {
    1638,        # Daha yeni sürüm zaten yüklü (MSI)
    1641,        # Başarılı, yeniden başlatma gerekiyor (MSI)
    0xE3826000,  # NVIDIA PhysX — zaten yüklü (3816972288)
    0xE3826001,  # NVIDIA PhysX — yeniden başlatma gerekli ama başarılı (3816972289)
}


class InstallError(Exception):
    pass


class InstallResult:
    def __init__(self, component_name, return_code, success,
                 restart_required=False, skipped=False, message="", log_path=""):
        self.component_name = component_name
        self.return_code = return_code
        self.success = success
        self.restart_required = restart_required
        self.skipped = skipped
        self.message = message
        self.log_path = log_path

    def __repr__(self):
        return (f"<InstallResult name={self.component_name!r} rc={self.return_code} "
                f"success={self.success} restart={self.restart_required}>")


def install_component(component: dict, file_path: str) -> InstallResult:
    name = component.get("name", Path(file_path).name if file_path else "Unknown")
    ext = Path(file_path).suffix.lower() if file_path else ""
    install_type = component.get("install_type", "")

    # ZIP — 'zip_run' alanı varsa arşivi açıp içindeki installer'ı çalıştır
    # (örn. OpenAL → oalinst.zip içindeki oalinst.exe). Alan yoksa eski
    # davranış korunur: otomatik çalıştırma engellenir, kullanıcıya bırakılır.
    if ext == ".zip":
        inner_exe = component.get("zip_run", "")
        if inner_exe:
            return _install_from_zip(name, file_path, inner_exe,
                                     list(component.get("silent_args", [])))
        logger.warning(f"ZIP file skipped (auto-run blocked): {file_path}")
        return InstallResult(name, -1, False, skipped=True,
                             message=f"{name} indirme klasörüne kaydedildi. "
                                     f"İçinden çıkan kurulum dosyasını manuel olarak çalıştırın: {file_path}")

    # Special: DirectX offline redistributable self-extractor
    if install_type == "directx_redist" or "directx_jun2010_redist" in Path(file_path).name.lower():
        return _install_directx_redist(name, file_path)

    # Special: .NET Framework 3.5 — indirme gerekmez, DISM ile Windows özelliği olarak etkinleştirilir
    if install_type == "dism_feature":
        feature = component.get("dism_feature", "")
        return _install_dism_feature(name, feature)

    # Special: VC++ 2005 — InstallShield tabanlı, birden fazla argüman kombinasyonu dener
    if install_type == "vcredist2005":
        return _install_vcredist2005(name, file_path)

    # Special: VC++ 2008 / 2010 — InstallShield tabanlı, fallback gerekebilir
    if install_type in ("vcredist2008", "vcredist2010"):
        return _install_vcredist_installshield(name, file_path)

    # Standard install
    silent_args: List[str] = list(component.get("silent_args", []))
    msi_log_path = ""

    if ext == ".msi":
        msi_log_path = _msi_log_path(file_path)
        cmd = _build_msi_command(file_path, silent_args, msi_log_path)
    else:
        cmd = [file_path] + silent_args

    logger.debug(f"Install command: {' '.join(str(c) for c in cmd)}")
    return _run_command(cmd, name, msi_log_path)


def _install_vcredist_installshield(name: str, file_path: str) -> InstallResult:
    """
    VC++ 2008 / 2010 Redistributable — InstallShield tabanlı.
    2005'e benzer fallback zinciri: /q:a /r:n → /Q:A /R:N → /quiet → /s
    """
    attempts = [
        [file_path, "/q:a", "/r:n"],   # InstallShield standart
        [file_path, "/Q:A", "/R:N"],   # Büyük harf varyant
        [file_path, "/quiet", "/norestart"],
        [file_path, "/q"],
        [file_path, "/s"],
    ]
    last_rc = -1
    for cmd in attempts:
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True,
                timeout=INSTALL_TIMEOUT,
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            rc = result.returncode
            if rc in (0, 3010, 1638, 1641):
                logger.info(f"{name} install OK with args {cmd[1:]}: rc={rc}")
                restart = rc in (3010, 1641)
                return InstallResult(name, rc, True, restart_required=restart,
                                     message="Installed successfully.")
            if rc == 1602:
                break
            last_rc = rc
            logger.debug(f"{name} attempt {cmd[1:]} → rc={rc}, trying next...")
        except Exception as exc:
            logger.debug(f"{name} attempt failed: {exc}")
    return InstallResult(name, last_rc, False,
                         message=f"{name} installation failed (rc={last_rc}). "
                                  "Try running the installer manually.")


def _install_vcredist2005(name: str, file_path: str) -> InstallResult:
    """
    VC++ 2005 Redistributable — InstallShield tabanlı installer.
    Farklı argüman kombinasyonlarını sırayla dener.
    """
    attempts = [
        [file_path, "/Q:A", "/R:N"],   # Standart sessiz kurulum
        [file_path, "/q:a", "/r:n"],   # Küçük harf varyant
        [file_path, "/Q"],              # Sadece sessiz
        [file_path, "/s"],              # Setup.exe tarzı
    ]
    last_rc = -1
    for cmd in attempts:
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True,
                timeout=INSTALL_TIMEOUT,
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            rc = result.returncode
            if rc in (0, 3010, 1638):
                logger.info(f"VC++ 2005 install OK with args {cmd[1:]}: rc={rc}")
                restart = rc == 3010
                return InstallResult(name, rc, True, restart_required=restart,
                                     message="Installed successfully.")
            if rc == 1602:  # Kullanıcı iptal
                break
            last_rc = rc
            logger.debug(f"VC++ 2005 attempt {cmd[1:]} → rc={rc}, trying next...")
        except Exception as exc:
            logger.debug(f"VC++ 2005 attempt failed: {exc}")
    return InstallResult(name, last_rc, False,
                         message=f"VC++ 2005 installation failed (rc={last_rc}). "
                                  "Try running the installer manually.")


def _install_from_zip(name: str, zip_path: str, inner_exe: str,
                      silent_args: List[str]) -> InstallResult:
    """
    ZIP arşivini geçici klasöre çıkarır ve içindeki *inner_exe* dosyasını
    silent_args ile sessizce çalıştırır (örn. OpenAL oalinst.exe /s).
    """
    import shutil
    import zipfile

    extract_dir = os.path.join(tempfile.gettempdir(),
                               f"RuntimeFix_zip_{Path(zip_path).stem}")
    if os.path.exists(extract_dir):
        try:
            shutil.rmtree(extract_dir)
        except OSError as exc:
            logger.warning(f"Could not remove old zip extract dir: {exc}")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    except (zipfile.BadZipFile, OSError) as exc:
        return InstallResult(name, -1, False,
                             message=f"Could not extract {Path(zip_path).name}: {exc}")

    # inner_exe'yi çıkarılan ağaçta büyük/küçük harf duyarsız ara
    target = None
    wanted = inner_exe.lower()
    for root, _dirs, files in os.walk(extract_dir):
        for fn in files:
            if fn.lower() == wanted:
                target = os.path.join(root, fn)
                break
        if target:
            break

    if not target:
        return InstallResult(name, -1, False,
                             message=f"{inner_exe} not found inside {Path(zip_path).name}.")

    logger.info(f"{name}: running {target} {' '.join(silent_args)}")
    return _run_command([target] + silent_args, name, "")


def _install_directx_redist(name: str, file_path: str) -> InstallResult:
    """DirectX Jun 2010 redist is a self-extractor; extract then run DXSETUP."""
    import shutil
    extract_dir = os.path.join(tempfile.gettempdir(), "DXRedist_AIO")
    # Temiz başlangıç — önceki çıkarma kalıntısı overwrite dialogu açabilir
    if os.path.exists(extract_dir):
        try:
            shutil.rmtree(extract_dir)
        except OSError as exc:
            logger.warning(f"Could not remove old DXRedist dir: {exc}")
    os.makedirs(extract_dir, exist_ok=True)
    logger.info(f"DirectX redist: extracting to {extract_dir}")

    _run_command([file_path, "/Q", "/Y", f"/T:{extract_dir}", "/C"], f"{name} [extract]", "")

    dxsetup = os.path.join(extract_dir, "DXSETUP.exe")
    if not os.path.exists(dxsetup):
        return InstallResult(name, -1, False,
                             message=f"DXSETUP.exe not found after extraction in {extract_dir}.")

    logger.info("DirectX redist: running DXSETUP.exe /silent")
    return _run_command([dxsetup, "/silent"], name, "")


def _run_command(cmd: List[str], name: str, log_path: str) -> InstallResult:
    try:
        # Kurulum pencerelerini gizle — InstallShield ve diğer GUI'li installer'lar için
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True,
            timeout=INSTALL_TIMEOUT,
            startupinfo=si,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise InstallError(f"Timed out after {INSTALL_TIMEOUT}s: {name}")
    except FileNotFoundError as exc:
        raise InstallError(f"Executable not found for {name!r}: {exc}") from exc
    except PermissionError as exc:
        raise InstallError(f"Permission denied for {name!r}: {exc}") from exc

    rc = result.returncode
    logger.debug(f"{name} -> rc={rc}\n  STDOUT: {result.stdout[:400]}\n  STDERR: {result.stderr[:400]}")

    if rc == RC_SUCCESS:
        return InstallResult(name, rc, True, message="Installed successfully.", log_path=log_path)
    if rc == RC_RESTART_REQUIRED or rc == 1641:
        return InstallResult(name, rc, True, restart_required=True,
                             message="Installed – restart required to complete.",
                             log_path=log_path)
    if rc == 1638:
        logger.info(f"{name}: newer version already installed (rc=1638), treating as success.")
        return InstallResult(name, rc, True, message="Already installed (newer version present).", log_path=log_path)
    if rc in RC_EXTRA_SUCCESS:
        logger.info(f"{name}: extra success code rc={rc}, treating as success.")
        return InstallResult(name, rc, True, message="Installed successfully (or already present).", log_path=log_path)
    return InstallResult(name, rc, False,
                         message=f"Installation failed (return code {rc}).",
                         log_path=log_path)


def _install_dism_feature(name: str, feature: str) -> InstallResult:
    """
    Windows özelliğini DISM ile etkinleştirir (indirme gerekmez).
    .NET Framework 3.5 gibi bileşenler için kullanılır.
    """
    if not feature:
        return InstallResult(name, -1, False, message="dism_feature belirtilmemiş.")

    cmd = [
        "dism.exe", "/online", "/enable-feature",
        f"/featurename:{feature}", "/All", "/NoRestart"
    ]
    logger.info(f"DISM: '{feature}' özelliği etkinleştiriliyor...")
    result = _run_command(cmd, name, "")

    # DISM başarı kodları: 0 = OK, 3010 = yeniden başlatma gerekli, 1 = zaten etkin (bazı sistemler)
    if not result.success and result.return_code == 1:
        return InstallResult(name, 1, True, message="Zaten etkin.")
    return result


def _build_msi_command(file_path: str, silent_args: List[str], log_path: str) -> List[str]:
    cmd = ["msiexec", "/i", file_path] + silent_args
    if "/norestart" not in cmd and "/forcerestart" not in cmd:
        cmd.append("/norestart")
    cmd.extend(["/L*v", log_path])
    return cmd


def _msi_log_path(installer_path: str) -> str:
    stem = Path(installer_path).stem
    log_path = os.path.join(tempfile.gettempdir(), f"{stem}_install.log")
    try:
        if os.path.exists(log_path):
            os.remove(log_path)
    except OSError:
        pass
    return log_path
