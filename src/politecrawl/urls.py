"""URL validation, normalization, scoping, and SSRF prevention.

The SSRF guard is the most important control here. A crawler follows links
supplied by pages it does not control; without this check a malicious page
could point the crawler at ``http://169.254.169.254/`` (cloud metadata) or
``http://localhost:6379/`` (an internal service). Every host is resolved and
rejected unless *all* of its addresses are public.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any, NamedTuple
from urllib.parse import urlsplit, urlunsplit

from .errors import SecurityError, ValidationError

ALLOWED_SCHEMES = frozenset({"http", "https"})

# A DNS resolver signature compatible with socket.getaddrinfo, injectable so
# tests never perform real network lookups.
Resolver = Callable[[str, int | None], list[tuple[Any, ...]]]


class SiteScope(NamedTuple):
    """Defines which hosts a crawl may visit."""

    host: str
    allow_subdomains: bool

    def contains(self, host: str) -> bool:
        host = host.lower()
        if host == self.host:
            return True
        return self.allow_subdomains and host.endswith("." + self.host)


def validate_url(url: str) -> str:
    """Validate a URL's shape (scheme, host, no credentials). Return it."""
    if not url or len(url) > 2000:
        raise ValidationError("URL is empty or unreasonably long")
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise ValidationError(f"unsupported URL scheme: {parts.scheme!r}")
    if not parts.hostname:
        raise ValidationError("URL has no host")
    if parts.username or parts.password:
        # Embedded credentials in URLs are a phishing/leak vector.
        raise ValidationError("URLs with embedded credentials are not allowed")
    return url


def normalize_url(url: str) -> str:
    """Canonicalize for deduplication: drop fragment, lowercase host."""
    parts = urlsplit(url)
    netloc = parts.hostname or ""
    if parts.port:
        default = {"http": 80, "https": 443}.get(parts.scheme)
        if parts.port != default:
            netloc = f"{netloc}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme, netloc, path, parts.query, ""))


def host_of(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise ValidationError("URL has no host")
    return host.lower()


def ensure_public_host(
    host: str, resolver: Resolver = socket.getaddrinfo
) -> None:
    """Raise :class:`SecurityError` unless every resolved address is public."""
    try:
        infos = resolver(host, None)
    except OSError as exc:
        raise SecurityError(f"cannot resolve host {host!r}") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise SecurityError(f"host {host!r} resolved to no addresses")

    for addr in addresses:
        ip = ipaddress.ip_address(addr.split("%")[0])  # strip zone id
        if not _is_public(ip):
            raise SecurityError(
                f"refusing non-public address {addr} for host {host!r}"
            )


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
