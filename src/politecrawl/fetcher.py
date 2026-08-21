"""Safe HTTP fetching.

Every fetch enforces: URL validation, an SSRF host check, an honest
User-Agent, explicit timeouts, retries with backoff on transient failures, a
response-size cap (defeating huge-response / decompression bombs), and a
content-type allowlist. Redirects are followed manually so each hop is
re-validated and re-checked for SSRF, rather than trusting requests to
follow a chain that could end at an internal address.

Following redirects by hand means ``requests`` never runs its own
``Session.rebuild_auth``, which is what normally strips ``Authorization`` when a
redirect crosses to another origin. That protection is reimplemented here: any
configured credential is sent only to the origin the fetch started on, so a
crawled site cannot 302 to a host it controls and collect the token.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

from .config import Settings
from .errors import ContentError, FetchError
from .logging_setup import sanitize_for_log
from .urls import ensure_public_host, host_of, validate_url

logger = logging.getLogger(__name__)


def _origin_of(url: str) -> tuple[str, str, int | None]:
    """Return (scheme, host, port) — the origin a credential is bound to."""
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


_RETRYABLE = {500, 502, 503, 504}
HostCheck = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
        host_check: HostCheck = ensure_public_host,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._session = session or requests.Session()
        self._owns = session is None
        self._host_check = host_check
        self._sleep = sleeper
        self._session.headers.update({"User-Agent": settings.user_agent})

    def close(self) -> None:
        if self._owns:
            self._session.close()

    def fetch(self, url: str, *, enforce_type: bool = True) -> FetchResult:
        """Fetch *url*, following validated redirects. Raise on any failure.

        *enforce_type* restricts the response to the HTML content-type
        allowlist; robots.txt fetches pass ``False`` to allow text/plain.
        """
        current = validate_url(url)
        # Credentials belong to the origin the caller asked for, not to whatever
        # a redirect chain happens to end at.
        credential_origin = _origin_of(current)
        for _hop in range(self.settings.max_redirects + 1):
            self._host_check(host_of(current))
            resp = self._request_with_retries(
                current, credential_origin=credential_origin
            )

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise FetchError(f"redirect without Location from {current}")
                current = validate_url(urljoin(current, location))
                logger.debug("redirect -> %s", sanitize_for_log(current))
                continue

            return self._finalize(resp, current, enforce_type)

        raise FetchError(f"too many redirects starting at {url}")

    def _request_with_retries(
        self, url: str, *, credential_origin: tuple[str, str, int | None] | None = None
    ) -> requests.Response:
        """GET *url*, retrying transient failures.

        ``credential_origin`` is the origin the configured credential belongs
        to. When the request has travelled to a different origin the credential
        is withheld — mirroring what ``requests`` does for a followed redirect.
        """
        headers = self.settings.auth_headers()
        same_origin = credential_origin is None or _origin_of(url) == credential_origin
        if headers and not same_origin:
            logger.debug(
                "withholding credentials on cross-origin redirect to %s",
                sanitize_for_log(url),
            )
            headers = {}

        last_exc: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                resp = self._session.get(
                    url,
                    timeout=self.settings.timeout,
                    stream=True,
                    allow_redirects=False,
                    headers=headers,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                if self._retry(attempt, reason=type(exc).__name__):
                    continue
                raise FetchError(
                    f"network error fetching {url}: {type(exc).__name__}"
                ) from exc

            if resp.status_code in _RETRYABLE and attempt < self.settings.max_retries:
                resp.close()
                self._retry(attempt, reason=f"HTTP {resp.status_code}")
                continue
            return resp
        raise FetchError(f"request failed: {url}") from last_exc

    def _finalize(
        self, resp: requests.Response, url: str, enforce_type: bool
    ) -> FetchResult:
        try:
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} for {url}")

            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if enforce_type and content_type and not self._allowed_type(content_type):
                raise ContentError(f"skipping content type {content_type!r}")

            declared = resp.headers.get("Content-Length")
            if (
                declared
                and declared.isdigit()
                and int(declared) > self.settings.max_bytes
            ):
                raise ContentError(f"response too large ({declared} bytes)")

            body = self._read_capped(resp)
            return FetchResult(
                url=url,
                status=resp.status_code,
                content_type=content_type,
                body=body,
            )
        finally:
            resp.close()

    def _read_capped(self, resp: requests.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > self.settings.max_bytes:
                raise ContentError(
                    f"response exceeded {self.settings.max_bytes} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _allowed_type(self, content_type: str) -> bool:
        return content_type.lower() in self.settings.content_types

    def _retry(self, attempt: int, *, reason: str) -> bool:
        if attempt >= self.settings.max_retries:
            return False
        delay = self.settings.backoff_base * (2**attempt)
        delay += random.uniform(0, self.settings.backoff_base)  # noqa: S311  # nosec B311
        logger.info("retry after %s (attempt %d, %.2fs)", reason, attempt + 1, delay)
        self._sleep(delay)
        return True
