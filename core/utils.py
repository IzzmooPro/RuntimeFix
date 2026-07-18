# -*- coding: utf-8 -*-
"""
utils.py - Utility / helper functions for RuntimeFix.
"""

import os
import sys
import logging
import logging.handlers
import ctypes
import platform
import subprocess
from typing import Optional

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
        import sys as _sys, tempfile as _tf
        if getattr(_sys, "frozen", False):
            _logs_dir = os.path.join(_tf.gettempdir(), "RuntimeFix_logs")
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
    return "".join(c for c in name if c.isalnum() or c in (".", "_", "-")) or "download.tmp"


# --------------------------------------------------------------------------
# Install-detection helpers
# --------------------------------------------------------------------------

def _silent_subprocess(cmd, timeout=15):
    """subprocess.run wrapper — pencere açmadan sessizce çalıştırır."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=timeout,
        startupinfo=si,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def detect_dotnet_sdk(version_prefix: str) -> bool:
    """
    Run `dotnet --list-sdks` and check whether any installed SDK starts with
    *version_prefix* (e.g. "8.0").
    """
    try:
        result = _silent_subprocess(["dotnet", "--list-sdks"])
        for line in result.stdout.splitlines():
            if line.startswith(version_prefix):
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


def detect_directx(min_version: str = "9") -> bool:
    """
    Detect DirectX installation by checking registry.
    Registry key varlığı yeterli — versiyon okuma hatası olsa bile True döner.
    """
    dx_registry_keys = [
        "HKLM\\SOFTWARE\\Microsoft\\DirectX",
        "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\DirectX",
    ]
    for key in dx_registry_keys:
        if detect_registry_key(key):
            logger.debug(f"DirectX detected via registry: {key}")
            return True

    # File-based fallback
    system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")
    dx_files = ["d3d9.dll", "d3d11.dll", "d3d12.dll", "dxgi.dll"]
    found = [f for f in dx_files if os.path.exists(os.path.join(system32, f))]
    if len(found) >= 2:
        logger.debug(f"DirectX detected via System32 DLLs: {found}")
        return True

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
    """Return True if the given absolute file path exists on disk."""
    exists = os.path.exists(file_path)
    logger.debug(f"File detection: {file_path} → {'found' if exists else 'not found'}")
    return exists


def detect_msxml4() -> bool:
    """
    MSXML 4.0 SP3 tespiti — birden fazla yöntemi sırayla dener.
    Modern Windows 10/11'de registry anahtarı farklı yerlerde olabilir.
    """
    import platform

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


def detect_java() -> bool:
    """Detect any installed Java Runtime via registry or PATH."""
    # Registry
    java_keys = [
        "HKLM\\SOFTWARE\\JavaSoft\\Java Runtime Environment",
        "HKLM\\SOFTWARE\\JavaSoft\\JRE",
        "HKLM\\SOFTWARE\\WOW6432Node\\JavaSoft\\Java Runtime Environment",
    ]
    for key in java_keys:
        if detect_registry_key(key):
            logger.debug(f"Java detected via registry: {key}")
            return True
    # PATH fallback — pencere gizli çalışır
    try:
        result = _silent_subprocess(["java", "-version"], timeout=10)
        if result.returncode == 0 or "version" in result.stderr.lower():
            logger.debug("Java detected via PATH")
            return True
    except Exception:
        pass
    return False


def detect_vsbuildtools() -> bool:
    """Detect Visual Studio Build Tools 2022 via registry."""
    keys = [
        "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\17.0",
        "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\VisualStudio\\17.0",
        # VS installer also writes here
        "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\Setup",
    ]
    # Check for BuildTools-specific path too
    build_tools_path = os.path.join(
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        "Microsoft Visual Studio", "2022", "BuildTools"
    )
    if os.path.exists(build_tools_path):
        logger.debug(f"VS Build Tools detected at: {build_tools_path}")
        return True
    for key in keys:
        if detect_registry_key(key):
            logger.debug(f"VS Build Tools detected via registry: {key}")
            return True
    return False


def is_component_installed(component: dict) -> bool:
    """
    Determine whether a component is already installed by consulting its
    ``detect_type`` and ``detect_value`` config fields.

    Supported detect_type values:
      dotnet    → dotnet --list-sdks
      registry  → Windows registry key check
      directx   → DirectX registry + DLL file check
      webview2  → WebView2 runtime registry check
      java      → Java registry + PATH check
      vsbuild   → VS Build Tools path + registry check
      file      → detect_value is an absolute file path
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
    if detect_type == "directx":
        return detect_directx(detect_value or "9")
    if detect_type == "webview2":
        return detect_webview2()
    if detect_type == "java":
        return detect_java()
    if detect_type == "vsbuild":
        return detect_vsbuildtools()
    if detect_type == "msxml4":
        return detect_msxml4()
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
        search = f"Visual C++ {normalized_year}"
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
                                        if search in dn and arch_match:
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

    # 1) Registry — hızlı, pencere açmaz
    if _WINREG_AVAILABLE and winreg is not None:
        reg_roots = [
            f"SOFTWARE\\dotnet\\Setup\\InstalledVersions\\{arch}\\sharedfx\\{runtime_name}",
            f"SOFTWARE\\WOW6432Node\\dotnet\\Setup\\InstalledVersions\\{arch}\\sharedfx\\{runtime_name}",
        ]
        for subkey in reg_roots:
            for flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                         winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, flag) as k:
                        for i in range(winreg.QueryInfoKey(k)[0]):
                            try:
                                ver = winreg.EnumKey(k, i)
                                if ver.startswith(version_prefix):
                                    logger.debug(f".NET {flavor} {version_prefix} {arch} found in registry")
                                    return True
                            except OSError:
                                pass
                except FileNotFoundError:
                    pass

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
            result = _silent_subprocess([exe, "--list-runtimes"])
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
