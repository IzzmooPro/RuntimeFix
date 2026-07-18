# -*- coding: utf-8 -*-
"""
security.py - Security enforcement for RuntimeFix.

Responsibilities:
  - HTTPS-only URL enforcement
  - Domain whitelist validation
  - SHA-256 file hash verification
"""

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Optional

logger = logging.getLogger("RuntimeFix.security")

# Default whitelist – also loaded dynamically from data/config.json at startup
DEFAULT_ALLOWED_DOMAINS: List[str] = [
    "builds.dotnet.microsoft.com",
    "download.microsoft.com",
    "download.visualstudio.microsoft.com",
    "aka.ms",
    "go.microsoft.com",
    "delivery.mp.microsoft.com",   # go.microsoft.com fwlink'lerin gerçek CDN hedefi
    "javadl.oracle.com",
    "sdlc-esd.oracle.com",   # javadl yönlendirmelerinin gerçek indirme sunucusu
    "download.oracle.com",
    "us.download.nvidia.com",
    "www.openal.org",
    "dl.openal.org",
]


class SecurityError(Exception):
    """Raised when a security check fails."""


class SecurityManager:
    """
    Centralised security gate for download URLs and downloaded files.

    Parameters
    ----------
    allowed_domains:
        Iterable of hostnames that are considered trusted.
        Sub-domains of a whitelisted host are automatically accepted
        (e.g. ``builds.dotnet.microsoft.com`` matches ``dotnet.microsoft.com``).
    """

    def __init__(self, allowed_domains: Optional[List[str]] = None) -> None:
        self._allowed_domains: List[str] = list(
            allowed_domains if allowed_domains is not None else DEFAULT_ALLOWED_DOMAINS
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_url(self, url: str) -> None:
        """
        Raise :class:`SecurityError` if *url* fails HTTPS or domain checks.

        Checks performed:
        1. Scheme must be ``https``.
        2. Hostname must match (or be a sub-domain of) an allowed domain.
        """
        parsed = urlparse(url)

        # 1 – HTTPS only
        if parsed.scheme.lower() != "https":
            raise SecurityError(
                f"Non-HTTPS URL rejected: {url!r}. Only HTTPS downloads are permitted."
            )

        # 2 – Domain whitelist
        hostname = (parsed.hostname or "").lower()
        if not self._is_allowed_host(hostname):
            raise SecurityError(
                f"Domain not whitelisted: {hostname!r}.\n"
                f"Allowed domains: {', '.join(self._allowed_domains)}"
            )

        logger.debug(f"URL passed security validation: {url}")

    def verify_sha256(self, file_path: str, expected_hash: str) -> None:
        """
        Compute the SHA-256 digest of *file_path* and compare it with
        *expected_hash* (case-insensitive hex string).

        Raises :class:`SecurityError` on mismatch, and also when
        *expected_hash* is empty/None — indirilen hiçbir dosya bütünlük
        denetimi olmadan kuruluma geçemez; config'e hash eklemek zorunludur.
        """
        if not expected_hash:
            raise SecurityError(
                f"No SHA-256 configured for {Path(file_path).name}. "
                f"Integrity cannot be verified — add the sha256 value to "
                f"data/config.json."
            )

        computed = self._compute_sha256(file_path)
        if computed.lower() != expected_hash.strip().lower():
            raise SecurityError(
                f"SHA-256 mismatch for {Path(file_path).name}!\n"
                f"  Expected : {expected_hash.lower()}\n"
                f"  Computed : {computed}"
            )

        logger.info(f"SHA-256 verified OK for {Path(file_path).name}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_allowed_host(self, hostname: str) -> bool:
        for domain in self._allowed_domains:
            domain = domain.lower()
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
        return False

    @staticmethod
    def _compute_sha256(file_path: str) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
