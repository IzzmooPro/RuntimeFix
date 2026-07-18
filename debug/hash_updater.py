# -*- coding: utf-8 -*-
"""
hash_updater.py - RuntimeFix data/config.json SHA-256 Otomatik Güncelleyici

Kullanım:
    python debug/hash_updater.py          (proje kökünden)
    python hash_updater.py                (debug/ klasöründen)

Ne yapar:
  1. data/config.json'daki tüm bileşenleri okur.
  2. Her bileşen için downloads/ cache'ine bakar — dosya varsa yeniden indirmez.
  3. Yoksa dosyayı indirir ve downloads/ klasörüne kaydeder.
  4. SHA-256 hesaplar ve data/config.json'a yazar.

Gereksinim: pip install requests
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("[HATA] 'requests' kütüphanesi bulunamadı.")
    print("       Lütfen çalıştırın: pip install requests")
    sys.exit(1)

# ── Yol ayarları ────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent          # debug/
_ROOT_DIR   = _SCRIPT_DIR.parent                       # proje kökü
CONFIG_PATH = _ROOT_DIR / "data" / "config.json"
CACHE_DIR   = _ROOT_DIR / "downloads"
CACHE_DIR.mkdir(exist_ok=True)

# ── HTTP ayarları ────────────────────────────────────────────────────────────
CHUNK_SIZE      = 65_536
CONNECT_TIMEOUT = 15
READ_TIMEOUT    = 180
USER_AGENT      = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _guess_filename(url: str, hint: str = "") -> str:
    if hint:
        return hint
    parsed = urlparse(url)
    name = unquote(Path(parsed.path).name)
    if name and "." in name:
        return name
    return "download.tmp"


def _find_cached(filename: str) -> Path | None:
    """Büyük/küçük harf farkı olmadan cache'de ara."""
    target = filename.lower()
    for f in CACHE_DIR.iterdir():
        if f.name.lower() == target and f.stat().st_size > 0:
            return f
    return None


def _download(session: requests.Session, url: str, dest: Path, name: str) -> None:
    resp = session.get(url, stream=True,
                       timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    start = time.time()

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(CHUNK_SIZE):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    speed = downloaded / (time.time() - start + 1e-9) / 1024 / 1024
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    print(f"\r  [{bar}] {pct:5.1f}%  {speed:.1f} MB/s", end="", flush=True)
    print()


def main():
    print("=" * 65)
    print("  RuntimeFix — SHA-256 Otomatik Hash Güncelleyici")
    print("=" * 65)
    print(f"  Config : {CONFIG_PATH}")
    print(f"  Cache  : {CACHE_DIR}")
    print()

    # Config yükle
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    components = cfg.get("components", [])
    print(f"Toplam {len(components)} bileşen bulundu.\n")

    session = _build_session()
    updated = 0
    skipped = 0
    errors  = []

    for idx, comp in enumerate(components, 1):
        name     = comp.get("name", f"Bileşen {idx}")
        url      = comp.get("url", "")
        hint     = comp.get("filename_hint", "")
        existing = comp.get("sha256", "")

        print(f"[{idx:02d}/{len(components)}] {name}")

        if not url:
            print("  ⚠ URL yok, atlanıyor.")
            skipped += 1
            continue

        filename = _guess_filename(url, hint)
        cached   = _find_cached(filename)

        # ── İndirme ──────────────────────────────────────────────────────
        if cached:
            print(f"  ✔ Cache bulundu: {cached.name}")
            file_path = cached
        else:
            dest = CACHE_DIR / filename
            print(f"  ↓ İndiriliyor: {filename}")
            try:
                _download(session, url, dest, name)
                file_path = dest
            except Exception as exc:
                print(f"  ✘ İndirme hatası: {exc}")
                errors.append((name, str(exc)))
                # Yarım kalan dosyayı temizle — bir sonraki çalıştırmada bozuk cache oluşmasın
                if dest.exists():
                    try:
                        dest.unlink()
                        print(f"  ⚠ Yarım dosya silindi: {dest.name}")
                    except OSError as rm_exc:
                        print(f"  ⚠ Yarım dosya silinemedi: {rm_exc}")
                continue

        # ── SHA-256 hesapla ───────────────────────────────────────────────
        print(f"  # SHA-256 hesaplanıyor...", end=" ", flush=True)
        sha = _sha256(file_path)
        print(sha[:16] + "...")

        if existing and existing.lower() == sha:
            print("  = Hash değişmedi.")
        else:
            comp["sha256"] = sha
            updated += 1
            print("  ✔ data/config.json güncellendi.")

        print()

    # ── Config kaydet ─────────────────────────────────────────────────────
    if updated > 0:
        # Yedek al
        backup = CONFIG_PATH.with_suffix(".json.bak")
        import shutil
        shutil.copy2(CONFIG_PATH, backup)
        print(f"Yedek alındı: {backup.name}")

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    # ── Özet ─────────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print(f"  Güncellenen : {updated} bileşen")
    print(f"  Atlanan     : {skipped} bileşen")
    print(f"  Hata        : {len(errors)} bileşen")
    if errors:
        print()
        print("  Hata veren bileşenler:")
        for n, e in errors:
            print(f"    - {n}: {e[:80]}")
    print("=" * 65)

    if updated == 0 and not errors:
        print("\nTüm hash'ler zaten güncel.")
    elif updated > 0:
        print(f"\ndata/config.json başarıyla güncellendi ({updated} hash eklendi).")

    input("\nDevam etmek için Enter'a basın...")


if __name__ == "__main__":
    main()
