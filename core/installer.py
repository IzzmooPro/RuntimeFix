# -*- coding: utf-8 -*-
"""
installer.py - Silent install engine for RuntimeFix.
"""

import logging
import os
import stat
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

from utils import dism_feature_state, run_hidden

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

# Farklı argümanlarla yeniden denemenin sonucu değiştirmeyeceği çıkış kodu
RC_NO_RETRY = {
    1602,  # Kullanıcı kurulumu iptal etti
}

# "Hiçbir şey yapılmadı" anlamına gelen kodlar. Kurulumda kabul edilebilir,
# onarımda başarısızlıktır.
RC_NOTHING_DONE = {
    1638,        # Bu ürünün başka bir sürümü zaten kurulu (MSI)
    0x80070666,  # Aynı anlamın Burn/HRESULT karşılığı
    -2147021722,  # 0x80070666'nın işaretli 32-bit okunuşu
}

# Bileşen sözlüğüne çalışma anında eklenen işaret: bu kurulum bir onarımdır
REPAIR_FLAG = "_repair"


class InstallError(Exception):
    pass


@dataclass
class InstallResult:
    component_name: str
    return_code: int
    success: bool
    restart_required: bool = False
    skipped: bool = False
    message: str = ""
    log_path: str = ""


def install_component(component: dict, file_path: str) -> InstallResult:
    name = component.get("name", Path(file_path).name if file_path else "Unknown")
    ext = Path(file_path).suffix.lower() if file_path else ""
    install_type = component.get("install_type", "")
    repair = bool(component.get(REPAIR_FLAG))

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
        cmd = _build_msi_command(file_path, silent_args, msi_log_path, repair=repair)
    elif repair and component.get("repair_args"):
        # Yayıncının onarım anahtarı (Burn tabanlı kurulumlarda /repair)
        cmd = [file_path] + list(component["repair_args"])
    else:
        cmd = [file_path] + silent_args

    logger.debug(
        f"{'Repair' if repair else 'Install'} command: "
        f"{' '.join(str(c) for c in cmd)}"
    )
    result = _run_command(cmd, name, msi_log_path)
    return _adjust_for_repair(result, repair)


def _adjust_for_repair(result: InstallResult, repair: bool) -> InstallResult:
    """
    Onarımda "zaten kurulu" bir başarı DEĞİLDİR.

    Kurulumda 1638 ("bu ürünün başka bir sürümü zaten kurulu") makul bir
    sonuçtur: hedef zaten sağlanmıştır. Onarımda ise aynı kod, kurulumun
    hiçbir şey yapmadan çıktığı anlamına gelir — kullanıcıya "onarıldı"
    demek yanlış olur.
    """
    if not repair or result.return_code not in RC_NOTHING_DONE:
        return result
    return InstallResult(
        result.component_name,
        result.return_code,
        False,
        message=(
            "Onarım yapılamadı: kurulum dosyası bileşenin zaten kurulu "
            "olduğunu bildirip hiçbir işlem yapmadan çıktı "
            f"(kod {result.return_code})."
        ),
        log_path=result.log_path,
    )


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
    return _run_install_attempts(name, attempts)


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
    return _run_install_attempts(name, attempts)


def _run_install_attempts(
    name: str, attempts: List[List[str]]
) -> InstallResult:
    last_result = InstallResult(name, -1, False)
    for cmd in attempts:
        try:
            result = _run_command(cmd, name, "")
        except InstallError as exc:
            # Süreç ya hiç başlamadı (eksik dosya, izin) ya da zamanında
            # bitmedi. Bunların hiçbiri argüman biçimine bağlı değil; denemeye
            # devam etmek çözmediği gibi her tur INSTALL_TIMEOUT kadar daha
            # bekletebilir (5 deneme × 15 dk = 75 dk donmuş görünen kurulum).
            logger.error(f"{name}: {exc} — argüman denemeleri durduruldu.")
            raise
        if result.success:
            logger.info(f"{name} install OK with args {cmd[1:]}: "
                        f"rc={result.return_code}")
            return result
        last_result = result
        if result.return_code in RC_NO_RETRY:
            # Kullanıcı iptali (1602) ya da kurulumun kendisinin başarısız
            # olması (1603) argüman biçiminden bağımsızdır; aynı installer'ı
            # 4 kez daha, her biri 15 dakikaya kadar çalıştırmanın anlamı yok.
            logger.info(
                f"{name}: rc={result.return_code} — argüman denemeleri durduruldu."
            )
            break
        logger.debug(
            f"{name} attempt {cmd[1:]} → rc={result.return_code}, "
            "trying next..."
        )
    last_result.message = (
        f"{name} installation failed (rc={last_result.return_code}). "
        "Try running the installer manually."
    )
    return last_result


def _install_from_zip(name: str, zip_path: str, inner_exe: str,
                      silent_args: List[str]) -> InstallResult:
    """
    ZIP arşivini geçici klasöre çıkarır ve içindeki *inner_exe* dosyasını
    silent_args ile sessizce çalıştırır (örn. OpenAL oalinst.exe /s).
    """
    try:
        with tempfile.TemporaryDirectory(prefix="RuntimeFix_zip_") as extract_dir:
            _safe_extract_zip(zip_path, extract_dir)

            # inner_exe'yi çıkarılan ağaçta büyük/küçük harf duyarsız ara
            target = None
            wanted = Path(inner_exe).name.lower()
            for root, _dirs, files in os.walk(extract_dir):
                for filename in files:
                    if filename.lower() == wanted:
                        target = os.path.join(root, filename)
                        break
                if target:
                    break

            if not target:
                return InstallResult(
                    name,
                    -1,
                    False,
                    message=(
                        f"{inner_exe} not found inside {Path(zip_path).name}."
                    ),
                )

            logger.info(f"{name}: running {target} {' '.join(silent_args)}")
            return _run_command([target] + silent_args, name, "")
    except (zipfile.BadZipFile, OSError, InstallError) as exc:
        return InstallResult(
            name,
            -1,
            False,
            message=f"Could not extract or run {Path(zip_path).name}: {exc}",
        )


def _safe_extract_zip(zip_path: str, destination: str) -> None:
    """Extract a ZIP only when every member stays inside *destination*."""
    destination_path = Path(destination).resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            mode = member.external_attr >> 16
            target_path = (destination_path / member_path).resolve()
            if (
                member_path.is_absolute()
                or member_path.drive
                or ".." in member_path.parts
                or ":" in member.filename
                or os.path.commonpath([destination_path, target_path])
                != str(destination_path)
                or stat.S_ISLNK(mode)
            ):
                raise InstallError(
                    f"Unsafe ZIP entry rejected: {member.filename!r}"
                )
        archive.extractall(destination_path)


def _install_directx_redist(name: str, file_path: str) -> InstallResult:
    """DirectX Jun 2010 redist is a self-extractor; extract then run DXSETUP."""
    with tempfile.TemporaryDirectory(prefix="RuntimeFix_DXRedist_") as extract_dir:
        logger.info(f"DirectX redist: extracting to {extract_dir}")
        extract_result = _run_command(
            [file_path, "/Q", "/Y", f"/T:{extract_dir}", "/C"],
            f"{name} [extract]",
            "",
        )
        if not extract_result.success:
            return InstallResult(
                name,
                extract_result.return_code,
                False,
                message=(
                    "DirectX arşivi çıkarılamadı "
                    f"(kod {extract_result.return_code})."
                ),
            )

        dxsetup = os.path.join(extract_dir, "DXSETUP.exe")
        if not os.path.isfile(dxsetup):
            return InstallResult(
                name,
                -1,
                False,
                message="DXSETUP.exe çıkarılan DirectX arşivinde bulunamadı.",
            )

        logger.info("DirectX redist: running DXSETUP.exe /silent")
        return _run_command([dxsetup, "/silent"], name, "")


def _run_hidden(cmd: List[str], timeout: int = INSTALL_TIMEOUT):
    """Kurulum komutunu pencere göstermeden çalıştırır (InstallShield vb. için)."""
    return run_hidden(cmd, timeout=timeout)


def _run_command(cmd: List[str], name: str, log_path: str) -> InstallResult:
    try:
        result = _run_hidden(cmd)
    except subprocess.TimeoutExpired:
        raise InstallError(f"Timed out after {INSTALL_TIMEOUT}s: {name}")
    except FileNotFoundError as exc:
        raise InstallError(f"Executable not found for {name!r}: {exc}") from exc
    except PermissionError as exc:
        raise InstallError(f"Permission denied for {name!r}: {exc}") from exc
    except OSError as exc:
        raise InstallError(f"Could not start installer for {name!r}: {exc}") from exc

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
        _system32_executable("dism.exe"), "/online", "/enable-feature",
        f"/featurename:{feature}", "/All", "/NoRestart"
    ]
    logger.info(f"DISM: '{feature}' özelliği etkinleştiriliyor...")
    result = _run_command(cmd, name, "")
    if result.success:
        return result

    # DISM'de 1 "zaten etkin" DEĞİL, genel hata kodudur. Başarısız çıkışta
    # özelliğin gerçek durumunu sorgula — yalnızca sahiden etkinse başarı say.
    state = dism_feature_state(feature)
    if state == "enabled":
        logger.info(f"DISM: '{feature}' zaten etkin (rc={result.return_code}).")
        return InstallResult(name, result.return_code, True, message="Zaten etkin.")
    if state == "enable pending":
        logger.info(f"DISM: '{feature}' etkinleştirildi, yeniden başlatma bekliyor.")
        return InstallResult(
            name, result.return_code, True, restart_required=True,
            message="Installed – restart required to complete.",
        )

    logger.error(f"DISM: '{feature}' etkinleştirilemedi (rc={result.return_code}, durum={state or 'bilinmiyor'}).")
    return InstallResult(
        name, result.return_code, False,
        message=(
            f"{name} etkinleştirilemedi (kod {result.return_code}). "
            "Bu özellik Windows Update üzerinden indirilir; Windows Update "
            "kapalıysa veya kurumsal ilkeyle engellendiyse etkinleştirilemez."
        ),
    )




def _build_msi_command(file_path: str, silent_args: List[str], log_path: str,
                       repair: bool = False) -> List[str]:
    # /fvomus: dosyaları ve registry girdilerini sürüm farkına bakmadan yeniden
    # yazar — MSI'ın gerçek onarım kipi. /i ise zaten kurulu üründe hiçbir şey
    # yapmadan 1638 döner.
    action = ["/fvomus", file_path] if repair else ["/i", file_path]
    cmd = [_system32_executable("msiexec.exe")] + action + silent_args
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


def _system32_executable(filename: str) -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(system_root, "System32", filename)
