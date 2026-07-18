# -*- coding: utf-8 -*-
"""
downloader.py - Robust HTTP downloader with offline cache support.

Cache logic:
  - Files are stored in <app_dir>/downloads/<filename>
  - If the cached file exists and is >0 bytes, it is reused (no re-download)
  - Cache can be bypassed by deleting the downloads/ folder
"""

import logging
import os
import time
from typing import Callable, Optional
from urllib.parse import urlparse, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils import sanitize_filename

logger = logging.getLogger("RuntimeFix.downloader")

CHUNK_SIZE     = 65_536
CONNECT_TIMEOUT = 15
READ_TIMEOUT    = 120
MAX_RETRIES     = 3
BACKOFF_FACTOR  = 1.5
USER_AGENT      = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Cache directory:
#   - PyInstaller exe olarak çalışırken → %TEMP%\RuntimeFix_downloads  (korumalı alana yazmayı önler)
#   - Normal Python ile çalışırken      → proje kökü/downloads/
import sys as _sys
import tempfile as _tempfile

if getattr(_sys, "frozen", False):
    # PyInstaller ile paketlenmiş exe
    CACHE_DIR = os.path.join(_tempfile.gettempdir(), "RuntimeFix_downloads")
else:
    # Kaynak koddan çalıştırma (geliştirme)
    _CORE_DIR = os.path.dirname(os.path.abspath(__file__))
    _ROOT_DIR = os.path.dirname(_CORE_DIR)
    CACHE_DIR = os.path.join(_ROOT_DIR, "downloads")


def _ensure_cache_dir() -> str:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        return CACHE_DIR
    except PermissionError:
        # CACHE_DIR yazılamıyorsa (örn. Program Files kısıtlaması) %TEMP%'e geç
        fallback = os.path.join(_tempfile.gettempdir(), "RuntimeFix_downloads")
        os.makedirs(fallback, exist_ok=True)
        logger.warning(f"Cache dir permission denied, using fallback: {fallback}")
        return fallback


def _build_session() -> requests.Session:
    session = requests.Session()
    retry_cfg = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_cfg)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = USER_AGENT
    # Oracle javadl için lisans kabul cookie'si gerekiyor
    session.cookies.set("oraclelicense", "accept-securebackup-cookie", domain="javadl.oracle.com")
    session.cookies.set("oraclelicense", "accept-securebackup-cookie", domain="sdlc-esd.oracle.com")
    return session


class DownloadError(Exception):
    pass


def download_file(
    url: str,
    dest_dir: str,                          # kept for API compatibility; cache overrides
    *,
    progress_cb: Optional[Callable[[str, int, float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    filename_hint: Optional[str] = None,    # aka.ms gibi redirect URL'ler için dosya adı ipucu
    url_validator: Optional[Callable[[str], None]] = None,  # redirect sonrası final URL denetimi
) -> str:
    """
    Download *url* to the offline cache directory and return the local path.
    If the file already exists in cache it is returned immediately.
    filename_hint: redirect URL'lerden dosya adı çözülemeyen durumlarda kullanılır.
    url_validator: verilirse redirect zinciri sonundaki URL'ye uygulanır;
                   whitelist dışına çıkan yönlendirmelerde exception fırlatmalıdır.
    """
    cache_dir = _ensure_cache_dir()
    filename  = filename_hint or resolve_filename_from_url(url)
    # Windows büyük/küçük harf: önce tam eşleşme, sonra case-insensitive tarama
    dest_path = os.path.join(cache_dir, filename)

    # ── Cache hit ─────────────────────────────────────────────────────────
    # Önce tam isimle bak, sonra aynı ismin farklı büyük/küçük varyantına bak
    _cached = find_cached(cache_dir, filename)
    if _cached:
        logger.info(f"Cache hit: {os.path.basename(_cached)} — skipping download.")
        if progress_cb:
            progress_cb(os.path.basename(_cached), 100, 0.0)
        return _cached

    # ── Download ──────────────────────────────────────────────────────────
    session = _build_session()
    try:
        response = session.get(
            url, stream=True,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise DownloadError(f"Network error downloading {url!r}: {exc}") from exc

    # Redirect zinciri whitelist dışına çıktıysa reddet
    if url_validator and response.url != url:
        url_validator(response.url)

    # Refine filename after redirect.
    # filename_hint her zaman kazanır: VC++ 2005/2008/2010 gibi bileşenlerin
    # sunucudaki dosya adları aynıdır (vcredist_x86.exe) — hint ezilirse
    # dosyalar cache'te birbirinin üzerine yazılır.
    if not filename_hint:
        final_filename = resolve_filename_from_url(response.url) or filename
        if final_filename != filename:
            dest_path = os.path.join(cache_dir, final_filename)
            filename  = final_filename

    total_size       = int(response.headers.get("content-length", 0))
    bytes_downloaded = 0
    start_time       = time.monotonic()

    size_str = f"{total_size/1_048_576:.1f} MB" if total_size else "unknown size"
    logger.info(f"Downloading: {filename} ({size_str})")

    # Önce .part geçici dosyasına indir — işlem yarıda kesilirse (elektrik,
    # kill vb.) cache'te bozuk ama "geçerli görünen" dosya kalmaz.
    part_path = dest_path + ".part"
    try:
        with open(part_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if cancel_check and cancel_check():
                    raise DownloadError("Download cancelled by user.")
                if not chunk:
                    continue
                fh.write(chunk)
                bytes_downloaded += len(chunk)
                if progress_cb:
                    elapsed   = time.monotonic() - start_time
                    speed     = (bytes_downloaded / (1_048_576 * elapsed)) if elapsed > 0 else 0.0
                    pct       = int((bytes_downloaded / total_size) * 100) if total_size > 0 else 0
                    progress_cb(filename, pct, speed)
        os.replace(part_path, dest_path)
    except DownloadError:
        _safe_remove(part_path)
        raise
    except Exception as exc:
        _safe_remove(part_path)
        raise DownloadError(f"Error saving {filename!r}: {exc}") from exc

    if progress_cb:
        elapsed = time.monotonic() - start_time
        speed   = (bytes_downloaded / (1_048_576 * elapsed)) if elapsed > 0 else 0.0
        progress_cb(filename, 100, speed)

    logger.info(f"Download complete → {dest_path}")
    return dest_path


def find_cached(cache_dir: str, filename: str) -> Optional[str]:
    """
    Cache klasöründe 'filename' ile eşleşen dosyayı bul.
    Windows'ta büyük/küçük harf duyarsız eşleşme yapar.
    """
    exact = os.path.join(cache_dir, filename)
    if os.path.exists(exact) and os.path.getsize(exact) > 0:
        return exact
    # Büyük/küçük harf varyantını ara
    lower = filename.lower()
    try:
        for entry in os.scandir(cache_dir):
            if entry.name.lower() == lower and entry.stat().st_size > 0:
                return entry.path
    except OSError:
        pass
    return None

# Geriye dönük uyumluluk için eski isim korunuyor
_find_cached = find_cached


def resolve_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name   = os.path.basename(unquote(parsed.path))
    if name and os.path.splitext(name)[1]:
        return sanitize_filename(name)
    return "downloaded_file.bin"

# Geriye dönük uyumluluk için eski isim korunuyor
_resolve_filename_from_url = resolve_filename_from_url


def _safe_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
