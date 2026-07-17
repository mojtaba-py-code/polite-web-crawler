"""URL validation, normalization, scoping, and SSRF-guard tests."""

from __future__ import annotations

import pytest

from politecrawl.errors import SecurityError, ValidationError
from politecrawl.urls import (
    SiteScope,
    ensure_public_host,
    host_of,
    normalize_url,
    validate_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "javascript:alert(1)",
        "mailto:a@b.com",
        "http://user:pass@example.com/",
        "not-a-url",
        "",
    ],
)
def test_invalid_urls_rejected(url):
    with pytest.raises(ValidationError):
        validate_url(url)


def test_valid_url_ok():
    assert validate_url("https://example.com/path?q=1") == "https://example.com/path?q=1"


def test_normalize_drops_fragment_and_default_port():
    assert normalize_url("https://Example.com:443/a#frag") == "https://example.com/a"
    assert normalize_url("http://x.com") == "http://x.com/"


def _resolver_for(ip):
    def resolver(host, port):
        return [(2, 1, 6, "", (ip, 0))]

    return resolver


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",       # loopback
        "10.0.0.5",        # private
        "192.168.1.10",    # private
        "169.254.169.254", # link-local (cloud metadata!)
        "::1",             # loopback v6
        "0.0.0.0",         # unspecified  # noqa: S104
    ],
)
def test_ssrf_blocks_non_public_addresses(ip):
    with pytest.raises(SecurityError):
        ensure_public_host("evil.example", resolver=_resolver_for(ip))


def test_ssrf_allows_public_address():
    # 93.184.216.34 is a public address (example.com historically).
    ensure_public_host("example.com", resolver=_resolver_for("93.184.216.34"))


def test_ssrf_blocks_if_any_address_is_private():
    def mixed(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("127.0.0.1", 0))]

    with pytest.raises(SecurityError):
        ensure_public_host("rebind.example", resolver=mixed)


def test_site_scope():
    scope = SiteScope("example.com", allow_subdomains=False)
    assert scope.contains("example.com")
    assert not scope.contains("evil.com")
    assert not scope.contains("sub.example.com")

    scope_sub = SiteScope("example.com", allow_subdomains=True)
    assert scope_sub.contains("sub.example.com")
    assert not scope_sub.contains("notexample.com")


def test_host_of():
    assert host_of("https://Example.com/x") == "example.com"
