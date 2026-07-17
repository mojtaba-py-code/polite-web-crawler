"""robots.txt policy tests."""

from __future__ import annotations

import responses

from politecrawl.fetcher import Fetcher
from politecrawl.robots import RobotsPolicy

ROBOTS = """
User-agent: *
Disallow: /private
Crawl-delay: 2
"""


def _policy(settings) -> RobotsPolicy:
    fetcher = Fetcher(settings, host_check=lambda _h: None, sleeper=lambda _s: None)
    return RobotsPolicy(fetcher, settings.user_agent)


@responses.activate
def test_disallow_is_respected(settings):
    responses.get(
        "https://example.com/robots.txt", body=ROBOTS, status=200,
        content_type="text/plain",
    )
    policy = _policy(settings)
    assert policy.can_fetch("https://example.com/public")
    assert not policy.can_fetch("https://example.com/private/x")


@responses.activate
def test_crawl_delay_parsed(settings):
    responses.get(
        "https://example.com/robots.txt", body=ROBOTS, status=200,
        content_type="text/plain",
    )
    policy = _policy(settings)
    assert policy.crawl_delay("https://example.com/") == 2.0


@responses.activate
def test_missing_robots_allows_all(settings):
    responses.get("https://example.com/robots.txt", status=404)
    policy = _policy(settings)
    assert policy.can_fetch("https://example.com/anything")


@responses.activate
def test_unreachable_robots_disallows(settings):
    responses.get("https://example.com/robots.txt", status=503)
    policy = _policy(settings)
    # Conservative: if robots can't be read, do not crawl.
    assert not policy.can_fetch("https://example.com/anything")


@responses.activate
def test_robots_result_is_cached(settings):
    responses.get(
        "https://example.com/robots.txt", body=ROBOTS, status=200,
        content_type="text/plain",
    )
    policy = _policy(settings)
    policy.can_fetch("https://example.com/a")
    policy.can_fetch("https://example.com/b")
    # Only one network call despite two checks.
    assert len(responses.calls) == 1
