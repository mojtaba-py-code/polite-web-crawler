"""End-to-end crawl tests against a small mocked site."""

from __future__ import annotations

import dataclasses

import responses

from politecrawl.crawler import Crawler
from politecrawl.fetcher import Fetcher
from politecrawl.ratelimit import RateLimiter


def _build_crawler(settings):
    fetcher = Fetcher(settings, host_check=lambda _h: None, sleeper=lambda _s: None)
    rate = RateLimiter(0.0, sleeper=lambda _s: None)
    return Crawler(settings, fetcher=fetcher, rate_limiter=rate)


def _page(links: list[str], title: str = "T") -> str:
    body = "".join(f'<a href="{href}">l</a>' for href in links)
    return f"<html><title>{title}</title><body>{body}</body></html>"


def _register(url: str, html: str) -> None:
    responses.get(url, body=html, status=200, content_type="text/html")


@responses.activate
def test_crawl_stays_on_site_and_bounds_pages(settings):
    responses.get("https://example.com/robots.txt", status=404)
    _register("https://example.com/", _page(
        ["/a", "/b", "https://other.com/x"]
    ))
    _register("https://example.com/a", _page([]))
    _register("https://example.com/b", _page([]))
    # other.com must never be requested.

    crawler = _build_crawler(settings)
    pages, stats = crawler.crawl("https://example.com/")

    urls = {p.url for p in pages}
    assert urls == {
        "https://example.com/",
        "https://example.com/a",
        "https://example.com/b",
    }
    assert stats.skipped_offsite >= 1
    assert not any("other.com" in c.request.url for c in responses.calls)


@responses.activate
def test_max_pages_enforced(settings):
    responses.get("https://example.com/robots.txt", status=404)
    settings = dataclasses.replace(settings, max_pages=2, max_depth=5)
    _register("https://example.com/", _page(["/a", "/b", "/c"]))
    for name in ("a", "b", "c"):
        _register(f"https://example.com/{name}", _page([]))

    crawler = _build_crawler(settings)
    pages, _stats = crawler.crawl("https://example.com/")
    assert len(pages) == 2


@responses.activate
def test_max_depth_enforced(settings):
    responses.get("https://example.com/robots.txt", status=404)
    settings = dataclasses.replace(settings, max_depth=1, max_pages=10)
    _register("https://example.com/", _page(["/a"]))
    _register("https://example.com/a", _page(["/b"]))
    _register("https://example.com/b", _page([]))

    crawler = _build_crawler(settings)
    pages, _ = crawler.crawl("https://example.com/")
    urls = {p.url for p in pages}
    # depth 0 (seed) and depth 1 (/a); /b at depth 2 is never enqueued.
    assert urls == {"https://example.com/", "https://example.com/a"}


@responses.activate
def test_robots_disallow_skips_page(settings):
    responses.get(
        "https://example.com/robots.txt",
        body="User-agent: *\nDisallow: /private\n",
        status=200,
        content_type="text/plain",
    )
    _register("https://example.com/", _page(["/private/x", "/ok"]))
    _register("https://example.com/ok", _page([]))
    # /private/x is registered but must be skipped by robots.
    _register("https://example.com/private/x", _page([]))

    crawler = _build_crawler(settings)
    pages, stats = crawler.crawl("https://example.com/")
    urls = {p.url for p in pages}
    assert "https://example.com/private/x" not in urls
    assert stats.skipped_robots >= 1


@responses.activate
def test_broken_page_does_not_abort_crawl(settings):
    responses.get("https://example.com/robots.txt", status=404)
    _register("https://example.com/", _page(["/good", "/bad"]))
    _register("https://example.com/good", _page([]))
    responses.get("https://example.com/bad", status=500)

    crawler = _build_crawler(settings)
    pages, stats = crawler.crawl("https://example.com/")
    urls = {p.url for p in pages}
    assert "https://example.com/good" in urls
    assert stats.errors >= 1
