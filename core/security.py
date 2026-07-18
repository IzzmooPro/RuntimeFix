# -*- coding: utf-8 -*-
"""
security.py - Security enforcement for RuntimeFix.

Responsibilities:
  - HTTPS-only URL enforcement
  - Domain whitelist validation
  - SHA-256 file hash verification
"""

import hashlib
import hmac
import logging
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Sequence

logger = logging.getLogger("RuntimeFix.security")

# Default whitelist – also loaded dynamically from data/config.json at startup
DEFAULT_ALLOWED_DOMAINS: list[str] = [
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
        Iterable of hostnames that are considered trusted. Subdomains of a
        whitelisted hostname are accepted (for example, ``cdn.example.com`` is
        accepted when ``example.com`` is listed).
    """

    def __init__(self, allowed_domains: Optional[Sequence[str]] = None) -> None:
        domains = (
            allowed_domains if allowed_domains is not None else DEFAULT_ALLOWED_DOMAINS
        )
        self._allowed_domains = self._normalise_domains(domains)

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

        if parsed.username or parsed.password:
            raise SecurityError(f"URL credentials are not permitted: {url!r}.")
        try:
            if parsed.port not in (None, 443):
                raise SecurityError(
                    f"Non-standard HTTPS port rejected: {parsed.port}."
                )
        except ValueError as exc:
            raise SecurityError(f"Invalid URL port: {url!r}.") from exc

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
        expected = (expected_hash or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise SecurityError(
                f"Invalid or missing SHA-256 for {Path(file_path).name}. "
                "A 64-character hexadecimal digest is required."
            )

        try:
            computed = self._compute_sha256(file_path)
        except OSError as exc:
            raise SecurityError(
                f"Could not read {Path(file_path).name} for SHA-256 verification: "
                f"{exc}"
            ) from exc
        if not hmac.compare_digest(computed, expected):
            raise SecurityError(
                f"SHA-256 mismatch for {Path(file_path).name}!\n"
                f"  Expected : {expected}\n"
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
    def _normalise_domains(domains: Sequence[str]) -> list[str]:
        normalised: list[str] = []
        for raw_domain in domains:
            domain = str(raw_domain).strip().lower().rstrip(".")
            if (
                not domain
                or "://" in domain
                or "/" in domain
                or ":" in domain
                or not re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                    domain,
                )
            ):
                raise ValueError(f"Invalid allowed domain: {raw_domain!r}")
            if domain not in normalised:
                normalised.append(domain)
        if not normalised:
            raise ValueError("At least one allowed download domain is required.")
        return normalised

    @staticmethod
    def _compute_sha256(file_path: str) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
