"""GitHub Releases üzerinden RuntimeFix güncellemelerini denetler ve indirir."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Optional
from urllib.parse import urlparse

from app_info import APP_NAME, GITHUB_LATEST_API_URL, GITHUB_REPO


class UpdateError(RuntimeError):
    """Güncelleme denetimi veya indirmesi tamamlanamadı."""


_TRUSTED_UPDATE_HOSTS = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


def _version_parts(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(
        r"v?(\d+)\.(\d+)(?:\.(\d+))?",
        (value or "").strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        raise UpdateError(f"Geçersiz sürüm biçimi: {value!r}")
    return tuple(int(part or 0) for part in match.groups())


def is_newer_version(latest: str, current: str) -> bool:
    return _version_parts(latest) > _version_parts(current)


def _validate_update_url(url: str) -> None:
    parsed = urlparse(url or "")
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or hostname not in _TRUSTED_UPDATE_HOSTS:
        raise UpdateError(f"Güvenilmeyen güncelleme adresi reddedildi: {url!r}")
    if parsed.username or parsed.password:
        raise UpdateError("Güncelleme adresinde kullanıcı bilgisi bulunamaz.")
    try:
        if parsed.port not in (None, 443):
            raise UpdateError("Güncelleme adresi standart dışı port kullanıyor.")
    except ValueError as exc:
        raise UpdateError(f"Geçersiz güncelleme adresi: {url!r}") from exc


def _request_json(url: str, timeout: int = 10) -> dict:
    _validate_update_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        # URL and redirect target are both restricted to exact GitHub HTTPS hosts.
        with urllib.request.urlopen(  # nosec B310
            request, timeout=timeout
        ) as response:
            _validate_update_url(response.geturl())
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(f"GitHub yayını bulunamadı: {GITHUB_REPO}") from exc
        raise UpdateError(f"GitHub yanıtı: HTTP {exc.code}") from exc
    except Exception as exc:
        raise UpdateError(str(exc)) from exc


def _pick_setup_asset(assets: list[dict], version: str) -> Optional[dict]:
    expected_name = f"{APP_NAME}-Setup-{version}.exe".lower()
    for asset in assets:
        if (
            str(asset.get("name", "")).lower() == expected_name
            and asset.get("browser_download_url")
        ):
            return asset
    return None


def check_latest_release(current_version: str) -> dict:
    release = _request_json(GITHUB_LATEST_API_URL)
    tag = str(release.get("tag_name") or release.get("name") or "").strip()
    latest_version = tag[1:] if tag.lower().startswith("v") else tag
    _version_parts(latest_version)
    asset = _pick_setup_asset(release.get("assets") or [], latest_version)

    return {
        "available": bool(
            latest_version and is_newer_version(latest_version, current_version)
        ),
        "version": latest_version,
        "tag": tag,
        "release_url": release.get("html_url"),
        "asset_name": asset.get("name") if asset else None,
        "download_url": asset.get("browser_download_url") if asset else None,
        "digest": asset.get("digest") if asset else None,
        "body": release.get("body") or "",
    }


def _digest_matches(path: str, digest: Optional[str]) -> bool:
    if not digest or ":" not in digest:
        return False
    algorithm, _, expected = digest.partition(":")
    expected = expected.strip().lower()
    if (
        algorithm.strip().lower() != "sha256"
        or not re.fullmatch(r"[0-9a-f]{64}", expected)
    ):
        return False

    hasher = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 256), b""):
            hasher.update(chunk)
    return hasher.hexdigest() == expected


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "")
    return cleaned.strip(" .") or f"{APP_NAME}-Setup.exe"


def download_update(
    info: dict,
    destination_dir: str,
    timeout: int = 30,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    url = info.get("download_url")
    if not url:
        raise UpdateError("Bu sürümde indirilebilir setup dosyası yok.")
    _validate_update_url(str(url))

    version = str(info.get("version") or "")
    _version_parts(version)
    expected_name = f"{APP_NAME}-Setup-{version}.exe"
    if str(info.get("asset_name") or "").lower() != expected_name.lower():
        raise UpdateError(
            f"Beklenen setup dosyası bulunamadı: {expected_name}"
        )

    os.makedirs(destination_dir, exist_ok=True)
    filename = _safe_filename(expected_name)
    final_path = os.path.join(destination_dir, filename)
    temporary_path = f"{final_path}.download"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{APP_NAME}-Updater"},
    )
    try:
        with (
            # Initial and final URLs are validated against exact GitHub HTTPS hosts.
            urllib.request.urlopen(request, timeout=timeout) as response,  # nosec B310
            open(temporary_path, "wb") as file,
        ):
            _validate_update_url(response.geturl())
            expected_size = int(response.headers.get("Content-Length") or 0)
            downloaded_size = 0
            while chunk := response.read(1024 * 256):
                if cancel_check and cancel_check():
                    raise UpdateError("Güncelleme indirmesi iptal edildi.")
                file.write(chunk)
                downloaded_size += len(chunk)
            if expected_size and downloaded_size != expected_size:
                raise UpdateError(
                    "Güncelleme dosyası eksik indirildi "
                    f"({downloaded_size}/{expected_size} bayt)."
                )

        if not _digest_matches(temporary_path, info.get("digest")):
            raise UpdateError(
                "İndirilen dosya doğrulanamadı "
                "(geçerli GitHub SHA-256 digest'i yok veya hash uyuşmadı)."
            )

        os.replace(temporary_path, final_path)
        return final_path
    except Exception as exc:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(str(exc)) from exc
