"""Immutable data types produced by a crawl."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Page:
    """A single scraped page."""

    url: str
    status: int
    depth: int
    title: str
    description: str
    headings: list[str]
    link_count: int
    content_hash: str
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CrawlStats:
    """Counters describing how a crawl went."""

    fetched: int = 0
    skipped_robots: int = 0
    skipped_visited: int = 0
    skipped_offsite: int = 0
    errors: int = 0
    blocked_security: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
