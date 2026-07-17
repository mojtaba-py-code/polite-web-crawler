"""Exception hierarchy.

Each class maps to a distinct handling strategy: validation/security errors
usually abort, fetch/content errors for a single page are logged and the
crawl continues to the next URL.
"""

from __future__ import annotations


class PolitecrawlError(Exception):
    """Base class for all politecrawl errors."""


class ConfigError(PolitecrawlError):
    """Invalid configuration or environment."""


class ValidationError(PolitecrawlError):
    """A URL or argument failed validation."""


class SecurityError(PolitecrawlError):
    """A security control blocked the request (SSRF, disallowed target)."""


class FetchError(PolitecrawlError):
    """A page could not be fetched (network, HTTP error, too many redirects)."""


class ContentError(FetchError):
    """The response was rejected (too large, wrong content type)."""


class CrawlError(PolitecrawlError):
    """A crawl-level problem (e.g. the seed itself is invalid)."""
