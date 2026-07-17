"""robots.txt compliance.

Fetches and caches each host's robots.txt through the same safe fetcher (so
robots requests are subject to the same SSRF and size protections), then
answers ``can_fetch`` and exposes the site's ``Crawl-delay``.

Policy on failures:
- No robots.txt (404) -> everything is allowed (the web's default).
- robots.txt present -> obey its rules for our User-Agent.
- Fetch error (network/5xx) -> be conservative and disallow, so a flaky or
  hostile server does not trick us into ignoring the rules.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .errors import FetchError, SecurityError
from .fetcher import Fetcher

logger = logging.getLogger(__name__)


class RobotsPolicy:
    def __init__(self, fetcher: Fetcher, user_agent: str) -> None:
        self._fetcher = fetcher
        self._agent = user_agent
        self._cache: dict[str, RobotFileParser | None] = {}
        # None in the cache means "fetch failed -> disallow everything".

    def _robots_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    def _load(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key in self._cache:
            return self._cache[key]

        parser = RobotFileParser()
        result: RobotFileParser | None = parser
        try:
            fetched = self._fetcher.fetch(self._robots_url(url), enforce_type=False)
            parser.parse(fetched.body.decode("utf-8", errors="replace").splitlines())
        except SecurityError:
            raise  # never swallow a security block
        except FetchError as exc:
            message = str(exc)
            if "HTTP 404" in message or "HTTP 410" in message:
                logger.debug("no robots.txt for %s; allowing", key)
                parser.parse([])  # empty rules -> allow all
            else:
                logger.warning("robots.txt unavailable for %s; disallowing", key)
                result = None  # fetch failed -> disallow everything
        self._cache[key] = result
        return result

    def can_fetch(self, url: str) -> bool:
        parser = self._load(url)
        if parser is None:
            return False
        return parser.can_fetch(self._agent, url)

    def crawl_delay(self, url: str) -> float | None:
        parser = self._load(url)
        if parser is None:
            return None
        delay = parser.crawl_delay(self._agent)
        return float(delay) if delay is not None else None
