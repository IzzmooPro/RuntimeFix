"""GitHub Releases üzerinden RuntimeFix güncellemelerini denetler ve indirir."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from app_info import APP_NAME, GITHUB_LATEST_API_URL, GITHUB_REPO


class UpdateError(RuntimeError):
    """Güncelleme denetimi veya indirmesi tamamlanamadı."""


def _version_parts(value: str) -> tuple[int, ...]:
    value = (value or "").strip().lower()
    if value.startswith("v"):
        value = value[1:]
    return tuple(int(part) for part in re.findall(r"\d+", value)) or (0,)


def is_newer_version(latest: str, current: str) -> bool:
    latest_parts = list(_version_parts(latest))
    current_parts = list(_version_parts(current))
    size = max(len(latest_parts), len(current_parts))
    latest_parts += [0] * (size - len(latest_parts))
    current_parts += [0] * (size - len(current_parts))
    return tuple(latest_parts) > tuple(current_parts)


def _request_json(url: str, timeout: int = 10) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(f"GitHub yayını bulunamadı: {GITHUB_REPO}") from exc
        raise UpdateError(f"GitHub yanıtı: HTTP {exc.code}") from exc
    except Exception as exc:
        raise UpdateError(str(exc)) from exc


def _pick_setup_asset(assets: list[dict]) -> Optional[dict]:
    executable_assets = [
        asset
        for asset in assets
        if str(asset.get("name", "")).lower().endswith(".exe")
        and asset.get("browser_download_url")
    ]
    if not executable_assets:
        return None

    preferred = [
        asset
        for asset in executable_assets
        if "setup" in str(asset.get("name", "")).lower()
        or "installer" in str(asset.get("name", "")).lower()
    ]
    return (preferred or executable_assets)[0]


def check_latest_release(current_version: str) -> dict:
    release = _request_json(GITHUB_LATEST_API_URL)
    tag = str(release.get("tag_name") or release.get("name") or "").strip()
    latest_version = tag[1:] if tag.lower().startswith("v") else tag
    asset = _pick_setup_asset(release.get("assets") or [])

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


def download_update(info: dict, destination_dir: str, timeout: int = 30) -> str:
    url = info.get("download_url")
    if not url:
        raise UpdateError("Bu sürümde indirilebilir setup dosyası yok.")

    os.makedirs(destination_dir, exist_ok=True)
    filename = _safe_filename(
        info.get("asset_name") or f"{APP_NAME}-Setup-{info.get('version')}.exe"
    )
    final_path = os.path.join(destination_dir, filename)
    temporary_path = f"{final_path}.download"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{APP_NAME}-Updater"},
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=timeout) as response,
            open(temporary_path, "wb") as file,
        ):
            while chunk := response.read(1024 * 256):
                file.write(chunk)

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
