"""politecrawl: a courteous, safety-first web crawler and scraper."""

from __future__ import annotations

from .config import Settings
from .crawler import Crawler
from .errors import (
    ContentError,
    CrawlError,
    FetchError,
    PolitecrawlError,
    SecurityError,
    ValidationError,
)
from .models import CrawlStats, Page

__version__ = "1.0.0"

__all__ = [
    "Crawler",
    "Settings",
    "Page",
    "CrawlStats",
    "PolitecrawlError",
    "ValidationError",
    "SecurityError",
    "FetchError",
    "ContentError",
    "CrawlError",
    "__version__",
]
