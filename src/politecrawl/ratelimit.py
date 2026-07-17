"""Per-host politeness throttle.

Enforces a minimum interval between requests to the same host so the crawler
never overwhelms a server. The effective delay is the larger of the site's
robots ``Crawl-delay`` and the configured default. A monotonic clock is used
so NTP adjustments cannot shrink or grow the interval.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        default_delay: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._default = default_delay
        self._clock = clock
        self._sleep = sleeper
        self._last: dict[str, float] = {}

    def wait(self, host: str, crawl_delay: float | None = None) -> None:
        """Block until it is polite to request *host* again."""
        delay = max(self._default, crawl_delay or 0.0)
        now = self._clock()
        last = self._last.get(host)
        if last is not None:
            elapsed = now - last
            if elapsed < delay:
                self._sleep(delay - elapsed)
        self._last[host] = self._clock()
