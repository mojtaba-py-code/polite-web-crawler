"""Shared fixtures. HTTP is mocked; DNS is faked via an injected host check."""

from __future__ import annotations

import pytest

from politecrawl.config import Settings
from politecrawl.fetcher import Fetcher


def allow_all_hosts(_host: str) -> None:
    """A host check that permits everything (bypasses real DNS in tests)."""
    return None


@pytest.fixture
def settings() -> Settings:
    return Settings(
        default_delay=0.0,  # no real waiting in tests
        max_pages=10,
        max_depth=2,
        max_bytes=1_000_000,
        max_retries=1,
        backoff_base=0.0,
    )


@pytest.fixture
def fetcher(settings: Settings) -> Fetcher:
    return Fetcher(
        settings,
        host_check=allow_all_hosts,
        sleeper=lambda _s: None,
    )
