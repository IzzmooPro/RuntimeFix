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
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Sequence

from utils import powershell_executable, run_hidden

logger = logging.getLogger("RuntimeFix.security")

# Authenticode doğrulaması — "evergreen" bileşenler için yedek denetim
SIGNATURE_TIMEOUT = 60
_SIGNATURE_PATH_ENV = "RUNTIMEFIX_VERIFY_PATH"
# Dosya yolu komut satırına gömülmez, ortam değişkeniyle geçirilir:
# tırnak/kaçış kaynaklı komut enjeksiyonu böyle tamamen dışarıda kalır.
_SIGNATURE_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    f"$s = Get-AuthenticodeSignature -LiteralPath $env:{_SIGNATURE_PATH_ENV};"
    "Write-Output ('STATUS=' + $s.Status);"
    "if ($s.SignerCertificate) "
    "{ Write-Output ('SUBJECT=' + $s.SignerCertificate.Subject) }"
)
# X.500 subject'te CN değeri virgül içeriyorsa tırnaklanır:
#   CN="Oracle America, Inc.", O="Oracle America, Inc.", ...
#   CN=Microsoft Corporation, O=Microsoft Corporation, ...
_CN_PATTERN = re.compile(r'CN=(?:"(?P<quoted>[^"]*)"|(?P<plain>[^,]*))')

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


def authenticode_signer(file_path: str) -> Optional[str]:
    """
    Dosyanın **geçerli** Authenticode imzasındaki yayıncı adını (CN) döndürür.

    İmza yoksa, geçersizse (bozuk/süresi dolmuş/güvenilmeyen kök) veya durum
    okunamazsa ``None`` döner — çağıran taraf bunu "doğrulanamadı" saymalıdır.
    """
    if os.name != "nt":
        return None

    environment = dict(os.environ)
    environment[_SIGNATURE_PATH_ENV] = os.path.abspath(file_path)
    command = [
        powershell_executable(),
        "-NoProfile", "-NonInteractive", "-Command", _SIGNATURE_SCRIPT,
    ]
    try:
        result = run_hidden(
            command, timeout=SIGNATURE_TIMEOUT, env=environment
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(f"Authenticode doğrulaması çalıştırılamadı: {exc}")
        return None

    status = ""
    subject = ""
    for line in (result.stdout or "").splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key == "STATUS":
            status = value.strip()
        elif key == "SUBJECT":
            subject = value.strip()

    if status.casefold() != "valid":
        logger.warning(
            f"{Path(file_path).name}: Authenticode durumu geçerli değil "
            f"({status or 'okunamadı'})."
        )
        return None

    match = _CN_PATTERN.search(subject)
    if not match:
        logger.warning(f"{Path(file_path).name}: imza sahibi (CN) okunamadı.")
        return None
    signer = (match.group("quoted") or match.group("plain") or "").strip()
    return signer or None


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

    def verify_download(self, file_path: str, component: dict) -> str:
        """
        İndirilen dosyayı doğrular; geçen denetimin adını döndürür.

        Öncelik her zaman SHA-256'dır. ``evergreen`` işaretli bileşenlerin
        URL'leri (aka.ms, fwlink, oracle /latest/) sürekli en yeni sürüme
        işaret ettiği için yayıncı yeni sürüm yayınladığında hash *doğal
        olarak* değişir; bu bir saldırı değildir ama hash'i körü körüne kabul
        etmek de doğrulamayı tamamen ortadan kaldırır.

        Bu durumda dosya, config'de belirtilen yayıncının **geçerli
        Authenticode imzası** ile doğrulanır. İmza yoksa, geçersizse ya da
        sertifikanın CN'i beklenen yayıncı değilse dosya reddedilir.

        Dönüş: ``"sha256"`` veya ``"signature"``.
        """
        expected_publisher = str(component.get("publisher") or "").strip()
        try:
            self.verify_sha256(file_path, component.get("sha256", ""))
            return "sha256"
        except SecurityError as hash_error:
            if not component.get("evergreen") or not expected_publisher:
                raise

            name = Path(file_path).name
            signer = authenticode_signer(file_path)
            if signer is None:
                raise SecurityError(
                    f"{name}: SHA-256 eşleşmedi ve dosyanın geçerli bir "
                    f"Authenticode imzası yok. Dosya reddedildi."
                ) from hash_error
            if signer.casefold() != expected_publisher.casefold():
                raise SecurityError(
                    f"{name}: SHA-256 eşleşmedi ve imza beklenen yayıncıya "
                    f"ait değil.\n  Beklenen : {expected_publisher}\n"
                    f"  İmzalayan: {signer}"
                ) from hash_error

            logger.warning(
                f"{name}: SHA-256 config'deki değerle eşleşmedi, ancak dosya "
                f"{signer} tarafından geçerli biçimde imzalanmış — yayıncı "
                f"büyük olasılıkla yeni sürüm yayınladı. İmza doğrulamasıyla "
                f"kabul edildi."
            )
            return "signature"

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
