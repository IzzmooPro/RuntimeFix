# -*- coding: utf-8 -*-
"""
debug_registry.py - RuntimeFix Registry Tanı Aracı
Sisteminizde hangi runtime'ların hangi GUID'lerle kayıtlı olduğunu gösterir.
Kullanım: python debug_registry.py
"""

import sys

print("=" * 70)
print("  RuntimeFix Registry Tanı Aracı")
print("=" * 70)

try:
    import winreg
except ImportError:
    print("[HATA] Bu araç sadece Windows'ta çalışır.")
    input("\nDevam etmek için Enter'a basın...")
    sys.exit(1)


def query_key(hive, path, name="", use_32bit=False):
    flags = winreg.KEY_READ
    if use_32bit:
        flags |= winreg.KEY_WOW64_32KEY
    else:
        flags |= winreg.KEY_WOW64_64KEY
    try:
        with winreg.OpenKey(hive, path, 0, flags) as k:
            if name == "":
                return True, None
            val, _ = winreg.QueryValueEx(k, name)
            return True, val
    except FileNotFoundError:
        return False, None
    except Exception as exc:
        return False, str(exc)


def scan_uninstall(keyword, use_32bit=False):
    """Uninstall anahtarlarında keyword içerenleri listele."""
    flags = winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
    if use_32bit:
        flags |= winreg.KEY_WOW64_32KEY
    else:
        flags |= winreg.KEY_WOW64_64KEY
    results = []
    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base, 0, flags) as uk:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(uk, i)
                    i += 1
                    try:
                        with winreg.OpenKey(uk, sub, 0, winreg.KEY_READ) as sk:
                            try:
                                dn, _ = winreg.QueryValueEx(sk, "DisplayName")
                                if keyword.lower() in dn.lower():
                                    results.append((sub, dn))
                            except FileNotFoundError:
                                pass
                    except Exception:
                        pass
                except OSError:
                    break
    except Exception:
        pass
    return results


def check_guid(label, guids):
    print(f"\n[{label}] Bilinen GUID'ler:")
    found = False
    for guid in guids:
        path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{guid}"
        ok64, _ = query_key(winreg.HKEY_LOCAL_MACHINE, path, use_32bit=False)
        ok32, _ = query_key(winreg.HKEY_LOCAL_MACHINE, path, use_32bit=True)
        if ok64:
            print(f"  ✓ BULUNDU [64bit]: HKLM\\{path}")
            found = True
        if ok32:
            print(f"  ✓ BULUNDU [32bit]: HKLM\\{path}")
            found = True
        if not ok64 and not ok32:
            print(f"  ✗ YOK: HKLM\\{path}")
    return found


# ─── VC++ 2005 ────────────────────────────────────────────────────────────────
check_guid("VC++ 2005 x86", [
    "{7299052b-02a4-4627-81f2-1818da5d550d}",
    "{A49F249F-0C91-497F-86DF-B2585E8E76B7}",
    "{710f4c1c-cc18-4c49-8cbf-51240c89a1a2}",
])

check_guid("VC++ 2005 x64", [
    "{071c9b48-7c32-4621-a0ac-3f809523288f}",
    "{6E8E85E8-CE4B-4FF5-91F7-04999C9FAE6A}",
    "{ad8a2fa1-06e7-4b0d-927d-6e54b3d31028}",
])

# ─── VC++ 2008 ────────────────────────────────────────────────────────────────
check_guid("VC++ 2008 x86", [
    "{9A25302D-30C0-39D9-BD6F-21E6EC160475}",
    "{FF66E9F6-83E7-3A3E-AF14-8DE9A809A6A4}",
    "{9BE518E6-ECC6-35A9-88E4-87755C07200F}",
])

check_guid("VC++ 2008 x64", [
    "{4B6C7001-C7D6-3710-913E-5BC23FCE91E6}",
    "{350AA351-21FA-3270-8B7A-835434E766AD}",
    "{5FCE6D76-F5DC-37AB-B2B8-22AB8CEDB1D4}",
])

# ─── VC++ 2010 ────────────────────────────────────────────────────────────────
check_guid("VC++ 2010 x86", [
    "{196BB40D-1578-3D01-B289-BEFC77A11A1E}",
    "{F0C3E5D1-1ADE-321E-8167-68EF0DE699A5}",
])

check_guid("VC++ 2010 x64", [
    "{DA5E371C-6333-3D8A-93A4-6FD5B20BCC6E}",
    "{1D8E6291-B0D5-35EC-8441-6616F567A0F7}",
])

# ─── VC++ 2012 ────────────────────────────────────────────────────────────────
check_guid("VC++ 2012 x86", [
    "{33d1fd90-4274-48a1-9bc1-97e33d9c2d6f}",
])

check_guid("VC++ 2012 x64", [
    "{ca67548a-5ebe-413a-b50c-4b9ceb6d66c6}",
])

# ─── VC++ 2013 ────────────────────────────────────────────────────────────────
check_guid("VC++ 2013 x86", [
    "{13A4EE12-23EA-3371-91EE-EFB36DDFFF3E}",
])

check_guid("VC++ 2013 x64", [
    "{A749D8E6-B613-3BE3-8F5F-045C84EBA29B}",
])

# ─── VC++ 2015-2022 ───────────────────────────────────────────────────────────
check_guid("VC++ 2015-2022 x86", [
    "{65E5BD06-6392-3027-8C26-853107D3CF1A}",
])

check_guid("VC++ 2015-2022 x64", [
    "{5af42f55-8e96-3849-8ea9-8024f0c31c58}",
    "{b11dc2da-6b65-3516-9e50-6616e8a96e50}",
])

# ─── DirectX ──────────────────────────────────────────────────────────────────
print("\n[DirectX] Registry:")
for use32, label in [(False, "64bit"), (True, "32bit")]:
    ok, val = query_key(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\DirectX", use_32bit=use32)
    status = "✓ BULUNDU" if ok else "✗ YOK"
    print(f"  {status} [{label}]: HKLM\\SOFTWARE\\Microsoft\\DirectX")
    ok, val = query_key(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\DirectX", use_32bit=use32)
    status = "✓ BULUNDU" if ok else "✗ YOK"
    print(f"  {status} [{label}]: HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\DirectX")

# ─── Tarama Sonuçları ─────────────────────────────────────────────────────────
for keyword in ["Visual C++ 2005", "Visual C++ 2008", "Visual C++ 2010",
                "Visual C++ 2012", "Visual C++ 2013", "Visual C++ 2015",
                "Visual C++ 2017", "Visual C++ 2019", "Visual C++ 2022",
                "DirectX", ".NET", "Java", "WebView2"]:
    results64 = scan_uninstall(keyword, use_32bit=False)
    results32 = scan_uninstall(keyword, use_32bit=True)
    # Wow64 path da dene
    results_wow = []
    try:
        import winreg as _wr
        base = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        with _wr.OpenKey(_wr.HKEY_LOCAL_MACHINE, base, 0, _wr.KEY_READ | _wr.KEY_ENUMERATE_SUB_KEYS) as uk:
            i = 0
            while True:
                try:
                    sub = _wr.EnumKey(uk, i)
                    i += 1
                    try:
                        with _wr.OpenKey(uk, sub, 0, _wr.KEY_READ) as sk:
                            try:
                                dn, _ = _wr.QueryValueEx(sk, "DisplayName")
                                if keyword.lower() in dn.lower():
                                    results_wow.append((sub, dn))
                            except FileNotFoundError:
                                pass
                    except Exception:
                        pass
                except OSError:
                    break
    except Exception:
        pass

    all_results = []
    for sub, dn in results64:
        all_results.append((f"64bit", f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{sub}", dn))
    for sub, dn in results32:
        all_results.append((f"32bit", f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{sub}", dn))
    for sub, dn in results_wow:
        all_results.append((f"WOW64", f"SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{sub}", dn))

    if all_results:
        print(f"\n[TARAMA] Uninstall'da '{keyword}' içerenler:")
        seen = set()
        for label, path, dn in all_results:
            key = (path, dn)
            if key not in seen:
                seen.add(key)
                print(f"  [{label}] {path}")
                print(f"    DisplayName: {dn}")

print("\n" + "=" * 70)
print("Bitti. Bu çıktıyı kopyalayıp paylaşın.")
print("=" * 70)
input("\nDevam etmek için Enter'a basın...")
