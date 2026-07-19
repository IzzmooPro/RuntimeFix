# -*- coding: utf-8 -*-
"""
check_config_drift.py — data/config.json'daki indirme adreslerini denetler.

Neden var: bileşen adresleri ve hash'leri zamanla bozulur. Microsoft bir
dosyayı taşır, Oracle BundleId'yi değiştirir, "evergreen" adresler yeni sürüme
geçtiği için hash tutmaz. Bu bozulmalar bugüne kadar ancak son kullanıcı
kurulum denerken ortaya çıkıyordu. Bu betik onları bakımcıya taşır.

Kullanım:
    python .github/scripts/check_config_drift.py                # yalnızca erişilebilirlik
    python .github/scripts/check_config_drift.py --hash evergreen
    python .github/scripts/check_config_drift.py --hash all

Çıkış kodu 0 = her şey yolunda, 1 = en az bir sorun bulundu.
Yalnızca standart kütüphane kullanır (CI'da bağımlılık kurulumu gerektirmez).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "data" / "config.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 60
CHUNK = 1024 * 256


def _request(url: str, extra_headers: dict | None = None) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT}
    # Oracle indirmeleri lisans kabul çerezi ister (downloader.py ile aynı davranış)
    if "oracle.com" in (urlparse(url).hostname or ""):
        headers["Cookie"] = "oraclelicense=accept-securebackup-cookie"
    headers.update(extra_headers or {})
    return urllib.request.Request(url, headers=headers)


def check_reachable(url: str) -> tuple[bool, str]:
    """İlk baytı isteyerek adresin canlı olduğunu doğrular (dosyayı indirmez)."""
    try:
        request = _request(url, {"Range": "bytes=0-0"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            response.read(1)
            status = getattr(response, "status", 200)
            final = response.geturl()
        note = f"HTTP {status}"
        if urlparse(final).hostname != urlparse(url).hostname:
            note += f" -> {urlparse(final).hostname}"
        return True, note
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # ağ hatası, DNS, TLS...
        return False, f"{type(exc).__name__}: {exc}"


def download_sha256(url: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as response:
        while chunk := response.read(CHUNK):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def main() -> int:
    # Windows konsolu cp1254 olabilir; Türkçe çıktı kodlama hatası vermesin
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hash",
        choices=("none", "evergreen", "all"),
        default="none",
        help="hangi bileşenlerin dosyası indirilip hash'i karşılaştırılsın",
    )
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    components = [c for c in config["components"] if c.get("url")]

    unreachable: list[str] = []
    drifted: list[str] = []

    print(f"{len(components)} indirilebilir bileşen denetleniyor...\n")
    for component in components:
        name = component["name"]
        url = component["url"]
        ok, note = check_reachable(url)
        print(f"[{'OK  ' if ok else 'FAIL'}] {name:44} {note}")
        if not ok:
            unreachable.append(f"{name}: {note} ({url})")
            continue

        wants_hash = args.hash == "all" or (
            args.hash == "evergreen" and component.get("evergreen")
        )
        if not wants_hash:
            continue

        try:
            digest, size = download_sha256(url)
        except Exception as exc:
            unreachable.append(f"{name}: indirme başarısız ({exc})")
            print(f"       indirme başarısız: {exc}")
            continue

        expected = (component.get("sha256") or "").lower()
        if digest == expected:
            print(f"       hash tamam ({size / 1_048_576:.1f} MB)")
        else:
            drifted.append(
                f"{name}\n    config : {expected}\n    gerçek : {digest}"
            )
            print(f"       HASH DEĞİŞMİŞ → {digest}")

    print()
    if unreachable:
        print("Erişilemeyen adresler:")
        for item in unreachable:
            print(f"  - {item}")
    if drifted:
        print("Hash'i değişen bileşenler (config güncellenmeli):")
        for item in drifted:
            print(f"  - {item}")
    if not unreachable and not drifted:
        print("Sapma yok.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
