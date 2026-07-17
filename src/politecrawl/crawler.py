"""The crawl loop: a bounded, polite, same-site breadth-first crawl.

Ties the pieces together with clear, safe defaults:
- stays within the seed's site (optionally its subdomains),
- honors robots.txt and per-host rate limits,
- bounds work by max_pages and max_depth,
- treats every fetched page and every discovered link as untrusted.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

from .config import Settings
from .errors import ContentError, FetchError, SecurityError, ValidationError
from .fetcher import Fetcher
from .logging_setup import sanitize_for_log
from .models import CrawlStats, Page
from .parser import parse_html
from .ratelimit import RateLimiter
from .robots import RobotsPolicy
from .urls import SiteScope, host_of, normalize_url, validate_url

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(
        self,
        settings: Settings,
        fetcher: Fetcher | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self._fetcher = fetcher or Fetcher(settings)
        self._rate = rate_limiter or RateLimiter(settings.default_delay)
        self._robots = RobotsPolicy(self._fetcher, settings.user_agent)

    def crawl(self, seed: str) -> tuple[list[Page], CrawlStats]:
        seed = normalize_url(validate_url(seed))
        scope = SiteScope(host_of(seed), self.settings.allow_subdomains)
        stats = CrawlStats()
        pages: list[Page] = []

        frontier: deque[tuple[str, int]] = deque([(seed, 0)])
        visited: set[str] = {seed}

        while frontier and len(pages) < self.settings.max_pages:
            url, depth = frontier.popleft()
            page = self._process(url, depth, scope, frontier, visited, stats)
            if page is not None:
                pages.append(page)

        logger.info(
            "crawl finished: %d pages, %d errors, %d robots-skipped",
            stats.fetched,
            stats.errors,
            stats.skipped_robots,
        )
        return pages, stats

    def _process(
        self,
        url: str,
        depth: int,
        scope: SiteScope,
        frontier: deque[tuple[str, int]],
        visited: set[str],
        stats: CrawlStats,
    ) -> Page | None:
        safe_url = sanitize_for_log(url)
        try:
            if not self._robots.can_fetch(url):
                logger.info("robots.txt disallows %s", safe_url)
                stats.skipped_robots += 1
                return None

            self._rate.wait(host_of(url), self._robots.crawl_delay(url))
            result = self._fetcher.fetch(url)
        except SecurityError as exc:
            logger.warning("blocked %s: %s", safe_url, exc)
            stats.blocked_security += 1
            return None
        except ContentError as exc:
            logger.info("skipped %s: %s", safe_url, exc)
            stats.errors += 1
            return None
        except (FetchError, ValidationError) as exc:
            logger.warning("failed %s: %s", safe_url, exc)
            stats.errors += 1
            return None

        extracted = parse_html(result.url, result.body)
        stats.fetched += 1

        if depth < self.settings.max_depth:
            self._enqueue(extracted.links, depth, scope, frontier, visited, stats)

        return Page(
            url=result.url,
            status=result.status,
            depth=depth,
            title=extracted.title,
            description=extracted.description,
            headings=extracted.headings,
            link_count=len(extracted.links),
            content_hash=extracted.content_hash,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def _enqueue(
        self,
        links: list[str],
        depth: int,
        scope: SiteScope,
        frontier: deque[tuple[str, int]],
        visited: set[str],
        stats: CrawlStats,
    ) -> None:
        budget = self.settings.max_pages - len(visited)
        for link in links:
            if budget <= 0:
                break
            if link in visited:
                continue
            try:
                if not scope.contains(host_of(link)):
                    stats.skipped_offsite += 1
                    continue
            except ValidationError:
                continue
            visited.add(link)
            frontier.append((link, depth + 1))
            budget -= 1

    def close(self) -> None:
        self._fetcher.close()

    def __enter__(self) -> Crawler:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
