# -*- coding: utf-8 -*-
"""
utils.py - Utility / helper functions for RuntimeFix.
"""

import json
import os
import re
import sys
import tempfile
import logging
import logging.handlers
import ctypes
import platform
import subprocess
import time

try:
    import winreg
    _WINREG_AVAILABLE = True
except ImportError:
    winreg = None  # type: ignore
    _WINREG_AVAILABLE = False


def setup_logging(log_file: str = "") -> logging.Logger:
    """
    Configure and return the application-wide logger with rotating file + console handlers.
    Log dosyası script'in yanına kaydedilir (çalışma dizinine değil).
    """
    logger = logging.getLogger("RuntimeFix")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger  # already configured

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Log dosyası konumu:
    #   exe → %TEMP%\RuntimeFix_logs\  (Program Files korumalı alan sorunu önlenir)
    #   Python → proje kökü/logs/
    if not log_file:
        import tempfile

        if getattr(sys, "frozen", False):
            _logs_dir = os.path.join(tempfile.gettempdir(), "RuntimeFix_logs")
        else:
            _core_dir = os.path.dirname(os.path.abspath(__file__))
            _root_dir = os.path.dirname(_core_dir)
            _logs_dir = os.path.join(_root_dir, "logs")
        os.makedirs(_logs_dir, exist_ok=True)
        log_file = os.path.join(_logs_dir, "aio_runtime.log")

    # Rotating file handler – max 5 MB, keep 3 backups
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


logger = setup_logging()


def is_admin() -> bool:
    """Return True if the current process has administrator/root privileges."""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.geteuid() == 0
    except Exception:
        logger.exception("is_admin() check failed")
        return False


def relaunch_as_admin() -> bool:
    """
    Relaunch the current script with elevated privileges via ShellExecute runas.
    Returns True if the elevation request was dispatched successfully.
    """
    if platform.system() != "Windows":
        return False
    extra = " ".join(f'"{a}"' for a in sys.argv[1:])
    if getattr(sys, "frozen", False):
        # PyInstaller exe: sys.executable zaten programın kendisi —
        # sys.argv[0]'ı parametre olarak tekrar geçirme.
        params = extra
    else:
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}" {extra}'.strip()
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        return result > 32
    except Exception:
        logger.exception("relaunch_as_admin() failed")
        return False


def sanitize_filename(name: str) -> str:
    """Strip characters that are unsafe for file system paths."""
    cleaned = "".join(
        char for char in name if char.isalnum() or char in (".", "_", "-")
    ).strip(" .")
    return cleaned or "download.tmp"


# --------------------------------------------------------------------------
# Install-detection helpers
# --------------------------------------------------------------------------

def powershell_executable() -> str:
    """Windows PowerShell'in tam yolu (PATH'e güvenilmez)."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
    )


def run_hidden(cmd, timeout: int = 15, env=None):
    """
    Komutu konsol penceresi açmadan çalıştırır.

    Tespit, kurulum ve imza doğrulamasının ortak alt katmanı — pencere gizleme
    bayrakları tek yerde tutulur. Windows dışında bayraklar atlanır, böylece
    modüller (ve testler) başka platformlarda da içe aktarılabilir.
    """
    kwargs = {}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs = {
            "startupinfo": si,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
    return subprocess.run(
        cmd,
        check=False, capture_output=True, text=True, timeout=timeout,
        env=env,
        # stdin AÇIKÇA kapatılır: pencere modunda paketlenmiş (konsolsuz) bir
        # uygulamada standart girdi tanıtıcısı geçersizdir ve devralan alt
        # süreç okumaya kalkarsa süresiz bloke olabilir. Kısayoldan açılan
        # kurulu sürümde taramanın kilitlenmesinin sebebi buydu.
        stdin=subprocess.DEVNULL,
        **kwargs,
    )




def dotnet_root(arch: str = "x64") -> str:
    """Mimariye göre .NET kurulum kökü."""
    if arch == "x86":
        base = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    else:
        base = os.environ.get("ProgramFiles", r"C:\Program Files")
    return os.path.join(base, "dotnet")


def _dotnet_versions_on_disk(relative_dir: str, arch: str = "x64") -> list[str]:
    """
    ``<dotnet kökü>/<relative_dir>`` altındaki sürüm klasörlerini listeler.

    En güvenilir ve en ucuz kaynak budur: .NET her sürümü kendi klasörüne
    kurar. Registry biçimi sürümden sürüme değişebiliyor, CLI ise alt süreç
    açmayı gerektiriyor.
    """
    directory = os.path.join(dotnet_root(arch), relative_dir)
    try:
        return [entry.name for entry in os.scandir(directory) if entry.is_dir()]
    except OSError:
        return []


def _dotnet_versions_in_registry(subkey: str) -> list[str]:
    """
    .NET kurulum anahtarındaki sürümleri okur.

    DİKKAT: sürümler alt anahtar DEĞİL, **değer adı** olarak tutulur
    (``"8.0.25" = 1``). Alt anahtar sayan eski kod her zaman boş dönüyor,
    bu yüzden tespit her seferinde CLI'ya düşüp gereksiz alt süreç açıyordu.
    """
    if not _WINREG_AVAILABLE or winreg is None:
        return []

    versions: list[str] = []
    for flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                 winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, flag) as key:
                value_count = winreg.QueryInfoKey(key)[1]
                for index in range(value_count):
                    try:
                        name, _value, _type = winreg.EnumValue(key, index)
                        if name:
                            versions.append(name)
                    except OSError:
                        break
        except (FileNotFoundError, OSError):
            continue
    return versions


def _matches_prefix(versions, version_prefix: str) -> bool:
    return any(str(v).startswith(version_prefix) for v in versions)


def detect_dotnet_sdk(version_prefix: str) -> bool:
    """
    .NET SDK tespiti (örn. "8.0").

    Sıra: disk → registry → CLI. İlk ikisi alt süreç açmaz; CLI yalnızca
    ikisi de sonuç veremezse denenir.
    """
    if _matches_prefix(_dotnet_versions_on_disk("sdk"), version_prefix):
        logger.debug(f".NET SDK {version_prefix} bulundu (disk)")
        return True

    for subkey in (r"SOFTWARE\dotnet\Setup\InstalledVersions\x64\sdk",
                   r"SOFTWARE\WOW6432Node\dotnet\Setup\InstalledVersions\x64\sdk"):
        if _matches_prefix(_dotnet_versions_in_registry(subkey), version_prefix):
            logger.debug(f".NET SDK {version_prefix} bulundu (registry)")
            return True

    try:
        result = run_hidden(["dotnet", "--list-sdks"])
        for line in (result.stdout or "").splitlines():
            if line.startswith(version_prefix):
                logger.debug(f".NET SDK {version_prefix} bulundu (CLI)")
                return True
        return False
    except FileNotFoundError:
        return False
    except Exception:
        logger.exception("dotnet SDK detection failed")
        return False


def detect_registry_key(reg_path: str) -> bool:
    """
    Check whether a Windows registry key exists.

    *reg_path* format: ``HKLM\\SOFTWARE\\...``
    """
    if not _WINREG_AVAILABLE or winreg is None:
        logger.warning("winreg not available – registry detection skipped.")
        return False

    HIVE_MAP = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
    }
    try:
        parts = reg_path.split("\\", 1)
        hive_str = parts[0].upper()
        subkey = parts[1] if len(parts) > 1 else ""
        hive = HIVE_MAP.get(hive_str, winreg.HKEY_LOCAL_MACHINE)

        # Try both 64-bit and 32-bit registry views
        for flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                     winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, subkey, 0, flag):
                    return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        logger.exception(f"Registry detection failed for: {reg_path}")
        return False


def detect_webview2() -> bool:
    """Detect Microsoft Edge WebView2 Runtime via registry."""
    keys = [
        # Per-machine (recommended) install path
        "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        # Per-user install path
        "HKCU\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        # Alternative machine key
        "HKLM\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    ]
    for key in keys:
        if detect_registry_key(key):
            logger.debug(f"WebView2 detected via registry: {key}")
            return True
    return False


def detect_file_exists(file_path: str) -> bool:
    """Return True if the given file path exists on disk.

    Yoldaki ortam değişkenleri (``%SystemRoot%``, ``%ProgramFiles(x86)%``)
    genişletilir. Config'e sabit ``C:\\Windows`` yazmak, Windows'un başka bir
    sürücüye kurulu olduğu sistemlerde bileşeni her zaman "eksik" gösteriyordu.
    """
    expanded = os.path.expandvars(file_path)
    exists = os.path.exists(expanded)
    logger.debug(f"File detection: {expanded} → {'found' if exists else 'not found'}")
    return exists


DISM_STATE_TIMEOUT = 120
# DISM'in "özellik açık" saydığı durumlar ("enable pending" = açık, yeniden
# başlatma bekliyor). /English ile çıktı dilden bağımsız sabittir.
DISM_ENABLED_STATES = ("enabled", "enable pending")


def dism_feature_state(feature: str) -> str:
    """
    ``dism /online /get-featureinfo`` çıktısından Windows özelliğinin durumunu
    okur. Dönüş: "enabled", "disabled", "enable pending" vb.; okunamazsa "".

    NOT: DISM yönetici yetkisi ister. Program zaten yükseltilmiş çalışır;
    yetkisiz bir ortamda sorgu boş döner ve özellik "kurulu değil" sayılır —
    yani belirsizlik hiçbir zaman "kurulu" yönünde yorumlanmaz.
    """
    if not feature:
        return ""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    cmd = [
        os.path.join(system_root, "System32", "dism.exe"),
        "/online", "/get-featureinfo", f"/featurename:{feature}", "/English",
    ]
    try:
        result = run_hidden(cmd, timeout=DISM_STATE_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug(f"DISM durum sorgusu başarısız ({feature}): {exc}")
        return ""

    for line in (result.stdout or "").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "state":
            return value.strip().lower()
    return ""


# Win32_OptionalFeature.InstallState değerleri
_WMI_INSTALL_STATES = {"1": "enabled", "2": "disabled", "3": "absent"}
# Özellik adı WQL sorgusuna gireceği için biçimi önceden kısıtlanır
_FEATURE_NAME_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
_WMI_FEATURE_ENV = "RUNTIMEFIX_FEATURE"
_WMI_FEATURE_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "$f = Get-CimInstance -ClassName Win32_OptionalFeature "
    f"-Filter (\"Name='\" + $env:{_WMI_FEATURE_ENV} + \"'\");"
    "if ($f) { Write-Output ('STATE=' + $f.InstallState) }"
)


def wmi_feature_state(feature: str) -> str:
    """
    Windows özelliğinin durumunu WMI (``Win32_OptionalFeature``) üzerinden okur.

    DISM'in aksine **yönetici yetkisi gerektirmez**, bu yüzden tespit için
    tercih edilir. Dönüş: "enabled" / "disabled" / "absent"; okunamazsa "".
    """
    if os.name != "nt" or not _FEATURE_NAME_PATTERN.fullmatch(feature or ""):
        return ""

    environment = dict(os.environ)
    environment[_WMI_FEATURE_ENV] = feature
    command = [
        powershell_executable(),
        "-NoProfile", "-NonInteractive", "-Command", _WMI_FEATURE_SCRIPT,
    ]
    try:
        result = run_hidden(command, timeout=25, env=environment)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(f"WMI özellik sorgusu başarısız ({feature}): {exc}")
        return ""

    for line in (result.stdout or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "STATE":
            return _WMI_INSTALL_STATES.get(value.strip(), "")
    return ""


def _feature_cache_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "RuntimeFix", "feature_cache.json")


def read_feature_cache() -> dict:
    """Son bilinen Windows özelliği durumlarını okur."""
    try:
        with open(_feature_cache_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_feature_cache(states: dict) -> None:
    path = _feature_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = dict(states)
        payload[_CACHE_TIMESTAMP_KEY] = time.time()
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError as exc:
        logger.debug(f"Özellik önbelleği yazılamadı: {exc}")


FEATURE_CACHE_TTL_SECONDS = 12 * 3600
_CACHE_TIMESTAMP_KEY = "_checked_at"


def feature_cache_is_stale(features) -> bool:
    """
    Arka plan sorgusunun gerekip gerekmediğini söyler.

    Sorgu alt süreç açtığı için mümkün olduğunca seyrek yapılır: yalnızca
    hiç bilinmeyen bir özellik varsa ya da kayıt eskidiyse. Böylece tipik
    açılışta program hiçbir alt süreç çalıştırmaz.
    """
    cache = read_feature_cache()
    if any(feature not in cache for feature in features):
        return True
    checked_at = cache.get(_CACHE_TIMESTAMP_KEY, 0)
    try:
        age = time.time() - float(checked_at)
    except (TypeError, ValueError):
        return True
    return age > FEATURE_CACHE_TTL_SECONDS


def remember_feature_state(feature: str, installed: bool) -> None:
    """Kurulum sonrası durumu hemen kaydeder (yeniden sorgulamaya gerek kalmaz)."""
    cache = read_feature_cache()
    cache[feature] = bool(installed)
    write_feature_cache(cache)


def detect_windows_feature_cached(feature: str) -> bool:
    """
    Windows özelliğini **alt süreç açmadan**, son bilinen değerden okur.

    Tarama sırasında yalnızca bu kullanılır: tespit için alt süreç açmak
    (WMI/DISM) paketlenmiş uygulamada arayüzü kilitleyebiliyor. Gerçek sorgu
    arayüz hazır olduktan sonra arka planda yapılır ve önbelleği tazeler.
    Bilinmeyen özellik "kurulu değil" sayılır.
    """
    return bool(read_feature_cache().get(feature, False))


def detect_windows_feature(feature: str) -> bool:
    """
    Windows özelliğinin açık olup olmadığını belirler.

    Neden dosya varlığına bakılmıyor: ``dplayx.dll`` DirectPlay özelliği
    kapalıyken de Windows'ta bulunur. Bu makinede ölçüldü — dosya var, özellik
    ``InstallState=2`` (devre dışı). Dosya tabanlı tespit bileşeni hep "kurulu"
    gösteriyordu.

    Önce WMI denenir (yetki istemez); WMI yanıt vermezse DISM'e düşülür.
    Hiçbiri okunamazsa "kurulu değil" denir — belirsizlik asla "kurulu"
    yönünde yorumlanmaz.
    """
    state = wmi_feature_state(feature)
    source = "WMI"
    if not state:
        state = dism_feature_state(feature)
        source = "DISM"

    installed = state in DISM_ENABLED_STATES
    logger.debug(
        f"Windows özelliği '{feature}': {source} durumu="
        f"{state or 'okunamadı'} → {'kurulu' if installed else 'kurulu değil'}"
    )
    return installed


def detect_msxml4() -> bool:
    """
    MSXML 4.0 SP3 tespiti — birden fazla yöntemi sırayla dener.
    Modern Windows 10/11'de registry anahtarı farklı yerlerde olabilir.
    """
    # 1) DLL dosyası kontrolü (en güvenilir yöntem)
    windir = os.environ.get("SystemRoot", "C:\\Windows")
    dll_paths = [
        os.path.join(windir, "SysWOW64", "msxml4.dll"),   # 64-bit Windows
        os.path.join(windir, "System32",  "msxml4.dll"),   # 32-bit Windows
    ]
    for dll in dll_paths:
        if os.path.isfile(dll):
            logger.debug(f"MSXML 4.0 detected via DLL: {dll}")
            return True

    # 2) Registry: SP3 subkey (WOW64 32-bit view)
    reg_paths = [
        "HKLM\\SOFTWARE\\Microsoft\\MSXML 4.0\\SP3",
        "HKLM\\SOFTWARE\\Microsoft\\MSXML 4.0",
        "HKLM\\SOFTWARE\\Microsoft\\Updates\\MSXML 4.0 SP3 Parser\\KB2758694",
    ]
    for rp in reg_paths:
        if detect_registry_key(rp):
            logger.debug(f"MSXML 4.0 detected via registry: {rp}")
            return True

    logger.debug("MSXML 4.0 not detected.")
    return False


def detect_java(arch: str = "") -> bool:
    """Detect Java Runtime, optionally distinguishing x86 from x64."""
    if arch not in {"", "x86", "x64"}:
        logger.warning(f"Unknown Java architecture in config: {arch!r}")
        return False

    if _WINREG_AVAILABLE and winreg is not None:
        views = {
            "x86": (winreg.KEY_WOW64_32KEY,),
            "x64": (winreg.KEY_WOW64_64KEY,),
            "": (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY),
        }
        keys = (
            r"SOFTWARE\JavaSoft\Java Runtime Environment",
            r"SOFTWARE\JavaSoft\JRE",
        )
        for key in keys:
            for view in views[arch]:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        key,
                        0,
                        winreg.KEY_READ | view,
                    ):
                        logger.debug(
                            f"Java {arch or 'any'} detected via registry: {key}"
                        )
                        return True
                except (FileNotFoundError, OSError):
                    continue

    # PATH does not reliably reveal x86/x64. Use it only for generic checks.
    if arch:
        return False
    try:
        result = run_hidden(["java", "-version"], timeout=10)
        if result.returncode == 0 or "version" in result.stderr.lower():
            logger.debug("Java detected via PATH")
            return True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(f"Java PATH detection failed: {exc}")
    return False


def is_component_installed(component: dict) -> bool:
    """
    Determine whether a component is already installed by consulting its
    ``detect_type`` and ``detect_value`` config fields.

    Supported detect_type values:
      dotnet    → dotnet --list-sdks
      registry  → Windows registry key check
      webview2  → WebView2 runtime registry check
      java      → Java registry + PATH check
      file      → detect_value is a file path (ortam değişkenleri genişletilir)
      windows_feature → Windows özelliği WMI/DISM'e sorulur (detect_value = özellik adı)
      none      → always returns False (not installed)
    """
    detect_type  = component.get("detect_type", "none")
    detect_value = component.get("detect_value", "")

    if detect_type == "dotnet":
        return detect_dotnet_sdk(detect_value)
    if detect_type == "dotnet_desktop":
        # detect_value format: "8.0:x64" veya "8.0:x64:aspnet"
        parts = detect_value.split(":")
        ver    = parts[0] if parts else detect_value
        arch   = parts[1] if len(parts) > 1 else "x64"
        flavor = parts[2] if len(parts) > 2 else "desktop"
        return detect_dotnet_desktop(ver, arch, flavor)
    if detect_type == "vcredist":
        # detect_value format: "2008:x64"
        parts = detect_value.split(":")
        year = parts[0] if parts else ""
        arch = parts[1] if len(parts) > 1 else "x86"
        return detect_vcredist(year, arch)
    if detect_type == "registry":
        return detect_registry_key(detect_value)
    if detect_type == "webview2":
        return detect_webview2()
    if detect_type == "java":
        return detect_java(detect_value)
    if detect_type == "msxml4":
        return detect_msxml4()
    if detect_type == "windows_feature":
        # Tarama alt süreç açmaz; gerçek sorgu arka planda tazelenir
        return detect_windows_feature_cached(detect_value)
    if detect_type == "file":
        return detect_file_exists(detect_value)
    if detect_type == "dotnet_framework":
        # detect_value = minimum Release DWORD (örn. "533320" for 4.8.1)
        min_rel = int(detect_value) if detect_value else 0
        return detect_dotnet_framework(min_rel)
    if detect_type == "dotnet_framework35":
        return detect_dotnet_framework35()
    if detect_type == "jdk":
        # detect_value = versiyon prefix'i, örn. "21" → "21.0.10" gibi subkey'leri tarar
        return detect_jdk_version(detect_value)

    # "none" or unknown → assume not installed
    return False


def detect_vcredist(year: str, arch: str) -> bool:
    """VC++ Redistributable tespiti — sürüm ve mimari bazlı çoklu registry path."""

    PATHS = {
        ("2005", "x86"): [
            # SP1 variants (farklı sistemlerde farklı GUID)
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{710f4c1c-cc18-4c49-8cbf-51240c89a1a2}",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{710f4c1c-cc18-4c49-8cbf-51240c89a1a2}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{7299052b-02a4-4627-81f2-1818da5d550d}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{A49F249F-0C91-497F-86DF-B2585E8E76B7}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{837b34e3-7c30-493c-8f6a-2b0f04e2912c}",
        ],
        ("2005", "x64"): [
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{ad8a2fa1-06e7-4b0d-927d-6e54b3d31028}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{071c9b48-7c32-4621-a0ac-3f809523288f}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{6E8E85E8-CE4B-4FF5-91F7-04999C9FAE6A}",
        ],
        ("2008", "x86"): [
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{9A25302D-30C0-39D9-BD6F-21E6EC160475}",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{9A25302D-30C0-39D9-BD6F-21E6EC160475}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{FF66E9F6-83E7-3A3E-AF14-8DE9A809A6A4}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{1F1C2DFC-2D24-3E06-BCB8-725134ADF989}",
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\9.0\\VC\\VCRedist\\x86",
        ],
        ("2008", "x64"): [
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{5FCE6D76-F5DC-37AB-B2B8-22AB8CEDB1D4}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{4B6C7001-C7D6-3710-913E-5BC23FCE91E6}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{350AA351-21FA-3270-8B7A-835434E766AD}",
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\9.0\\VC\\VCRedist\\x64",
        ],
        ("2010", "x86"): [
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{196BB40D-1578-3D01-B289-BEFC77A11A1E}",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{196BB40D-1578-3D01-B289-BEFC77A11A1E}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{F0C3E5D1-1ADE-321E-8167-68EF0DE699A5}",
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\10.0\\VC\\VCRedist\\x86",
        ],
        ("2010", "x64"): [
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{DA5E371C-6333-3D8A-93A4-6FD5B20BCC6E}",
            "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{1D8E6291-B0D5-35EC-8441-6616F567A0F7}",
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\10.0\\VC\\VCRedist\\x64",
        ],
        ("2012", "x86"): [
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\11.0\\VC\\Runtimes\\x86",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\11.0\\VC\\Runtimes\\x86",
        ],
        ("2012", "x64"): [
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\11.0\\VC\\Runtimes\\x64",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\11.0\\VC\\Runtimes\\x64",
        ],
        ("2013", "x86"): [
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\12.0\\VC\\Runtimes\\x86",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\12.0\\VC\\Runtimes\\x86",
        ],
        ("2013", "x64"): [
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\12.0\\VC\\Runtimes\\x64",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\12.0\\VC\\Runtimes\\x64",
        ],
        ("2015", "x86"): [
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x86",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x86",
        ],
        ("2015", "x64"): [
            "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64",
        ],
    }

    # "2015-2022" gibi geniş etiketleri "2015" olarak normalize et
    normalized_year = year.split("-")[0] if "-" in year else year

    # Bilinen GUID path'leri dene
    for path in PATHS.get((normalized_year, arch), PATHS.get((year, arch), [])):
        if detect_registry_key(path):
            logger.debug(f"VC++ {year} {arch} detected: {path}")
            return True

    # Fallback: Programs & Features listesini tara (hem 64 hem 32bit view)
    if not _WINREG_AVAILABLE or winreg is None:
        return False
    try:
        uninstall_roots = [
            "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
            "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        ]
        search = f"visual c++ {normalized_year}"
        for root in uninstall_roots:
            for flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                         winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root, 0, flag) as base:
                        for i in range(winreg.QueryInfoKey(base)[0]):
                            try:
                                sub_name = winreg.EnumKey(base, i)
                                with winreg.OpenKey(base, sub_name, 0, flag) as sub:
                                    try:
                                        dn, _ = winreg.QueryValueEx(sub, "DisplayName")
                                        # x86 sürümlerin DisplayName'inde mimari etiketi
                                        # YOKTUR ("Microsoft Visual C++ 2005 Redistributable");
                                        # x64 sürümler "(x64)" / "x64" içerir. Bu yüzden
                                        # x86 = "x64 geçmeyen", x64 = "x64 geçen" kabul edilir.
                                        dn_l = dn.lower()
                                        arch_match = ("x64" in dn_l) if arch == "x64" else ("x64" not in dn_l)
                                        if search in dn_l and arch_match:
                                            logger.debug(f"VC++ {year} {arch} found via scan: {dn}")
                                            return True
                                    except FileNotFoundError:
                                        pass
                            except OSError:
                                pass
                except FileNotFoundError:
                    pass
    except Exception as e:
        logger.debug(f"VC++ scan error: {e}")
    return False


def detect_dotnet_desktop(version_prefix: str, arch: str = "x64", flavor: str = "desktop") -> bool:
    """
    .NET Desktop Runtime veya ASP.NET Core Runtime tespiti.
    Önce registry'e bakar (hızlı, pencere açmaz), sonra CLI fallback.
    flavor: "desktop" = Microsoft.WindowsDesktop.App
            "aspnet"  = Microsoft.AspNetCore.App
    """
    runtime_name = (
        "Microsoft.AspNetCore.App" if flavor == "aspnet"
        else "Microsoft.WindowsDesktop.App"
    )

    # 1) Disk — en güvenilir kaynak, alt süreç ve registry biçimi bağımlılığı yok
    if _matches_prefix(
        _dotnet_versions_on_disk(os.path.join("shared", runtime_name), arch),
        version_prefix,
    ):
        logger.debug(f".NET {flavor} {version_prefix} {arch} bulundu (disk)")
        return True

    # 2) Registry — sürümler DEĞER adı olarak tutulur (alt anahtar değil)
    for subkey in (
        f"SOFTWARE\\dotnet\\Setup\\InstalledVersions\\{arch}\\sharedfx\\{runtime_name}",
        f"SOFTWARE\\WOW6432Node\\dotnet\\Setup\\InstalledVersions\\{arch}\\sharedfx\\{runtime_name}",
    ):
        if _matches_prefix(_dotnet_versions_in_registry(subkey), version_prefix):
            logger.debug(f".NET {flavor} {version_prefix} {arch} bulundu (registry)")
            return True

    # 2) CLI fallback — mimari bazlı dotnet.exe çalıştır (x86 için x86 dotnet'i dene)
    # Program Files (x86) altındaki dotnet x86 runtime'larını, normal altındaki x64'ü listeler.
    if arch == "x86":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        dotnet_exe = os.path.join(pf86, "dotnet", "dotnet.exe")
    else:
        pf64 = os.environ.get("ProgramFiles", r"C:\Program Files")
        dotnet_exe = os.path.join(pf64, "dotnet", "dotnet.exe")

    # x86 için YALNIZCA Program Files (x86)\dotnet\dotnet.exe güvenilirdir;
    # PATH'teki dotnet x64'tür ve x86 sorgusunda yanlış pozitif üretir.
    if arch == "x86":
        candidates = [dotnet_exe]
    else:
        candidates = [dotnet_exe, "dotnet"]
    for exe in candidates:
        try:
            result = run_hidden([exe, "--list-runtimes"])
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and runtime_name in parts[0] and parts[1].startswith(version_prefix):
                    logger.debug(f".NET {flavor} {version_prefix} {arch} found via CLI ({exe})")
                    return True
        except FileNotFoundError:
            continue
        except Exception:
            break

    return False


def detect_jdk_version(version_prefix: str) -> bool:
    """
    Oracle JDK tespiti — HKLM\\SOFTWARE\\JavaSoft\\JDK altındaki subkey'leri tarar.
    JDK 17+ sürümleri "21.0.10" gibi tam versiyon numarasıyla kaydolur.
    version_prefix örneği: "21" → "21.0.10" gibi subkey'leri bulur.
    """
    if not _WINREG_AVAILABLE or winreg is None:
        return False

    key_path = r"SOFTWARE\JavaSoft\JDK"
    for flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                 winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, flag) as k:
                i = 0
                while True:
                    try:
                        subkey = winreg.EnumKey(k, i)
                        if subkey.startswith(version_prefix):
                            logger.debug(f"JDK {version_prefix} detected: subkey={subkey}")
                            return True
                        i += 1
                    except OSError:
                        break
        except (FileNotFoundError, OSError):
            pass
    return False


def detect_dotnet_framework(min_release: int = 0) -> bool:
    """
    .NET Framework 4.x tespiti — registry Release DWORD değerini kontrol eder.

    Release referans değerleri:
      4.8   → 528040 (Win10 1903+), 528049 (diğer)
      4.8.1 → 533320 (Win11 22H2+), 533325 (diğer)
    """
    if not _WINREG_AVAILABLE or winreg is None:
        return False

    key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
    for flag in (winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
                 winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, flag) as k:
                release, _ = winreg.QueryValueEx(k, "Release")
                if int(release) >= min_release:
                    logger.debug(f".NET Framework 4.x detected: Release={release} (min={min_release})")
                    return True
        except (FileNotFoundError, OSError):
            pass
    return False


def detect_dotnet_framework35() -> bool:
    """
    .NET Framework 3.5 tespiti — registry Install değerini kontrol eder.
    """
    if not _WINREG_AVAILABLE or winreg is None:
        return False

    key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5"
    for flag in (winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
                 winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, flag) as k:
                install, _ = winreg.QueryValueEx(k, "Install")
                if install == 1:
                    logger.debug(".NET Framework 3.5 detected in registry")
                    return True
        except (FileNotFoundError, OSError):
            pass
    return False
