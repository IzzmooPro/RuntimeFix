# -*- coding: utf-8 -*-
"""
Tespit denetimi: programın is_component_installed() sonuçlarını,
programın tespit kodunu KULLANMAYAN bağımsız kanıtlarla karşılaştırır.
"""
import json
import os
import re
import subprocess
import sys
import winreg

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
from utils import is_component_installed

WIN = os.environ.get("SystemRoot", r"C:\Windows")
PF = os.environ.get("ProgramFiles", r"C:\Program Files")
PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

def _run(cmd):
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=20, startupinfo=si).stdout
    except Exception:
        return ""

# Programlar ve Özellikler görünen adları (bağımsız kaynak)
def arp_names():
    names = []
    roots = [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]
    for root in roots:
        for flag in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root, 0,
                                    winreg.KEY_READ | flag) as base:
                    for i in range(winreg.QueryInfoKey(base)[0]):
                        try:
                            with winreg.OpenKey(base, winreg.EnumKey(base, i)) as sub:
                                dn, _ = winreg.QueryValueEx(sub, "DisplayName")
                                names.append(dn)
                        except OSError:
                            pass
            except FileNotFoundError:
                pass
    return names

ARP = arp_names()
DOTNET_RT = _run(["dotnet", "--list-runtimes"])
DOTNET_SDK = _run(["dotnet", "--list-sdks"])
JAVA_VER = _run(["java", "-version"]) or ""

def arp_has(pattern):
    rx = re.compile(pattern, re.IGNORECASE)
    return any(rx.search(n) for n in ARP)

def f(*p):  # dosya var mı
    return os.path.exists(os.path.join(*p))

def d(*p):  # klasör deseni var mı (glob)
    import glob
    return bool(glob.glob(os.path.join(*p)))

def vc(year, arch):
    tag = "x64" if arch == "x64" else "x86"
    if year == "2015":
        pat = rf"Visual C\+\+ 20(15|17|19|22|25|26).*\({tag}\)"
    else:
        if arch == "x64":
            pat = rf"Visual C\+\+ {year}.*(x64)"
        else:
            # 2005/2008 x86 adında mimari yazmaz — 'x64 geçmeyen' kabul edilir
            rx64 = re.compile(rf"Visual C\+\+ {year}.*x64", re.IGNORECASE)
            rx = re.compile(rf"Visual C\+\+ {year}", re.IGNORECASE)
            return any(rx.search(n) and not rx64.search(n) for n in ARP)
    return arp_has(pat)

def dotnet_rt(prefix, kind):
    return any(l.startswith(kind) and l.split()[1].startswith(prefix)
               for l in DOTNET_RT.splitlines() if l.strip())

# Bileşen adı → bağımsız kanıt fonksiyonu
INDEP = {
    "VC++ Redist 2005 (x86)": lambda: vc("2005", "x86"),
    "VC++ Redist 2005 (x64)": lambda: vc("2005", "x64"),
    "VC++ Redist 2008 (x86)": lambda: vc("2008", "x86") or f(WIN, "SysWOW64", "msvcr90.dll"),
    "VC++ Redist 2008 (x64)": lambda: vc("2008", "x64"),
    "VC++ Redist 2010 (x86)": lambda: f(WIN, "SysWOW64", "msvcr100.dll"),
    "VC++ Redist 2010 (x64)": lambda: f(WIN, "System32", "msvcr100.dll"),
    "VC++ Redist 2012 (x86)": lambda: f(WIN, "SysWOW64", "msvcr110.dll"),
    "VC++ Redist 2012 (x64)": lambda: f(WIN, "System32", "msvcr110.dll"),
    "VC++ Redist 2013 (x86)": lambda: f(WIN, "SysWOW64", "msvcr120.dll"),
    "VC++ Redist 2013 (x64)": lambda: f(WIN, "System32", "msvcr120.dll"),
    "VC++ Redist 2015-2022 (x86)": lambda: f(WIN, "SysWOW64", "vcruntime140.dll"),
    "VC++ Redist 2015-2022 (x64)": lambda: f(WIN, "System32", "vcruntime140.dll"),
    ".NET Desktop Runtime 6.0 (x86)": lambda: d(PF86, "dotnet", "shared", "Microsoft.WindowsDesktop.App", "6.0*"),
    ".NET Desktop Runtime 6.0 (x64)": lambda: dotnet_rt("6.0", "Microsoft.WindowsDesktop.App"),
    ".NET Desktop Runtime 7.0 (x86)": lambda: d(PF86, "dotnet", "shared", "Microsoft.WindowsDesktop.App", "7.0*"),
    ".NET Desktop Runtime 7.0 (x64)": lambda: dotnet_rt("7.0", "Microsoft.WindowsDesktop.App"),
    ".NET Desktop Runtime 8.0 (x86)": lambda: d(PF86, "dotnet", "shared", "Microsoft.WindowsDesktop.App", "8.0*"),
    ".NET Desktop Runtime 8.0 (x64)": lambda: dotnet_rt("8.0", "Microsoft.WindowsDesktop.App"),
    ".NET Desktop Runtime 9.0 (x86)": lambda: d(PF86, "dotnet", "shared", "Microsoft.WindowsDesktop.App", "9.0*"),
    ".NET Desktop Runtime 9.0 (x64)": lambda: dotnet_rt("9.0", "Microsoft.WindowsDesktop.App"),
    ".NET Desktop Runtime 10.0 (x86)": lambda: d(PF86, "dotnet", "shared", "Microsoft.WindowsDesktop.App", "10.0*"),
    ".NET Desktop Runtime 10.0 (x64)": lambda: dotnet_rt("10.0", "Microsoft.WindowsDesktop.App"),
    "ASP.NET Core Runtime 6.0 (x64)": lambda: dotnet_rt("6.0", "Microsoft.AspNetCore.App"),
    "ASP.NET Core Runtime 8.0 (x64)": lambda: dotnet_rt("8.0", "Microsoft.AspNetCore.App"),
    "ASP.NET Core Runtime 9.0 (x64)": lambda: dotnet_rt("9.0", "Microsoft.AspNetCore.App"),
    "ASP.NET Core Runtime 10.0 (x64)": lambda: dotnet_rt("10.0", "Microsoft.AspNetCore.App"),
    ".NET SDK 6.0 (x64)": lambda: any(l.startswith("6.0") for l in DOTNET_SDK.splitlines()),
    ".NET SDK 8.0 (x64)": lambda: any(l.startswith("8.0") for l in DOTNET_SDK.splitlines()),
    ".NET SDK 9.0 (x64)": lambda: any(l.startswith("9.0") for l in DOTNET_SDK.splitlines()),
    ".NET SDK 10.0 (x64)": lambda: any(l.startswith("10.0") for l in DOTNET_SDK.splitlines()),
    "DirectX End-User Runtime Web Installer": lambda: f(WIN, "System32", "D3DX9_43.dll"),
    "DirectX Offline Redistributable (Jun 2010)": lambda: f(WIN, "System32", "D3DX9_43.dll"),
    "DirectPlay (Eski Oyun Desteği)": lambda: f(WIN, "SysWOW64", "dplayx.dll"),
    "Vulkan Runtime": lambda: f(WIN, "System32", "vulkan-1.dll"),
    "WebView2 Runtime": lambda: d(PF86, "Microsoft", "EdgeWebView", "Application", "*"),
    "OpenAL": lambda: f(WIN, "SysWOW64", "OpenAL32.dll") or f(WIN, "System32", "OpenAL32.dll"),
    "Java 8 Runtime (JRE) (x86)": lambda: d(PF86, "Java", "jre*"),
    "Java 8 Runtime (JRE) (x64)": lambda: d(PF, "Java", "jre*") or '"1.8' in JAVA_VER,
    "Java SE Development Kit 21": lambda: d(PF, "Java", "jdk-21*"),
    "MSXML 4.0 SP3 Parser": lambda: f(WIN, "SysWOW64", "msxml4.dll") or f(WIN, "System32", "msxml4.dll"),
    "NVIDIA PhysX System Software": lambda: d(PF86, "NVIDIA Corporation", "PhysX", "*") or arp_has(r"NVIDIA PhysX"),
    "XNA Framework Redistributable 3.1": lambda: d(WIN, "Microsoft.NET", "XNA", "Framework", "v3.1") or arp_has(r"XNA Framework.*3\.1"),
    "XNA Framework Redistributable 4.0 Refresh": lambda: d(WIN, "Microsoft.NET", "XNA", "Framework", "v4.0") or arp_has(r"XNA Framework.*4\.0"),
    "VS 2010 Tools for Office Runtime": lambda: d(PF86, "Common Files", "Microsoft Shared", "VSTO", "10.0") or arp_has(r"Visual Studio 2010 Tools for Office"),
    ".NET Framework 3.5": lambda: f(WIN, "Microsoft.NET", "Framework", "v3.5"),
    ".NET Framework 4.8.1": lambda: f(WIN, "Microsoft.NET", "Framework64", "v4.0.30319", "clr.dll"),
}

cfg = json.load(open(os.path.join(ROOT, "data", "config.json"), encoding="utf-8"))
match = mismatch = 0
mismatches = []
print(f"{'Bileşen':<44} {'Program':<8} {'Bağımsız':<9} Sonuç")
print("-" * 74)
for comp in cfg["components"]:
    name = comp["name"]
    app_says = is_component_installed(comp)
    fn = INDEP.get(name)
    if fn is None:
        print(f"{name:<44} {'?':<8} {'?':<9} KONTROL YOK")
        continue
    indep = bool(fn())
    ok = app_says == indep
    match += ok
    mismatch += (not ok)
    mark = "EŞLEŞTİ" if ok else "UYUŞMUYOR ✘"
    if not ok:
        mismatches.append(name)
    print(f"{name:<44} {'kurulu' if app_says else 'eksik':<8} "
          f"{'kurulu' if indep else 'eksik':<9} {mark}")

print("-" * 74)
print(f"SONUÇ: {match} eşleşti, {mismatch} uyuşmadı")
if mismatches:
    print("Uyuşmayanlar:", ", ".join(mismatches))
sys.exit(1 if mismatch else 0)
