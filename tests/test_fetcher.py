"""Fetcher tests: SSRF wiring, size cap, content-type, redirects, retries."""

from __future__ import annotations

import dataclasses

import pytest
import responses

from politecrawl.errors import ContentError, FetchError, SecurityError
from politecrawl.fetcher import Fetcher


def _deny(_host: str) -> None:
    raise SecurityError("blocked by policy")


@responses.activate
def test_ssrf_check_is_enforced(settings):
    # Even with a valid mock, a failing host check must block the fetch.
    responses.get("https://internal.example/", body="x", status=200)
    fetcher = Fetcher(settings, host_check=_deny, sleeper=lambda _s: None)
    with pytest.raises(SecurityError):
        fetcher.fetch("https://internal.example/")


@responses.activate
def test_successful_html_fetch(fetcher):
    responses.get(
        "https://example.com/",
        body="<html><title>Hi</title></html>",
        status=200,
        content_type="text/html",
    )
    result = fetcher.fetch("https://example.com/")
    assert result.status == 200
    assert b"<title>Hi</title>" in result.body


@responses.activate
def test_non_html_content_type_rejected(fetcher):
    responses.get(
        "https://example.com/data.json",
        json={"a": 1},
        status=200,
    )
    with pytest.raises(ContentError):
        fetcher.fetch("https://example.com/data.json")


@responses.activate
def test_oversize_by_content_length_rejected(settings):
    fetcher = Fetcher(
        dataclasses.replace(settings, max_bytes=100),
        host_check=lambda _h: None,
        sleeper=lambda _s: None,
    )
    responses.get(
        "https://example.com/big",
        body="x" * 500,
        status=200,
        content_type="text/html",
        headers={"Content-Length": "500"},
    )
    with pytest.raises(ContentError):
        fetcher.fetch("https://example.com/big")


@responses.activate
def test_oversize_by_streaming_rejected(settings):
    # No Content-Length header: the cap must trigger while streaming.
    fetcher = Fetcher(
        dataclasses.replace(settings, max_bytes=100),
        host_check=lambda _h: None,
        sleeper=lambda _s: None,
    )
    responses.get(
        "https://example.com/big",
        body="x" * 5000,
        status=200,
        content_type="text/html",
    )
    with pytest.raises(ContentError):
        fetcher.fetch("https://example.com/big")


@responses.activate
def test_redirect_is_followed_and_revalidated(fetcher):
    responses.get(
        "https://example.com/old",
        status=301,
        headers={"Location": "https://example.com/new"},
    )
    responses.get(
        "https://example.com/new",
        body="<html><title>New</title></html>",
        status=200,
        content_type="text/html",
    )
    result = fetcher.fetch("https://example.com/old")
    assert result.url == "https://example.com/new"


@responses.activate
def test_redirect_to_private_host_is_blocked(settings):
    # host check allows the public seed but denies the redirect target.
    def selective(host):
        if host == "internal.local":
            raise SecurityError("private")
        return None

    fetcher = Fetcher(settings, host_check=selective, sleeper=lambda _s: None)
    responses.get(
        "https://example.com/go",
        status=302,
        headers={"Location": "https://internal.local/secret"},
    )
    with pytest.raises(SecurityError):
        fetcher.fetch("https://example.com/go")


@responses.activate
def test_server_error_retried_then_raised(fetcher):
    for _ in range(5):
        responses.get("https://example.com/", status=503)
    with pytest.raises(FetchError):
        fetcher.fetch("https://example.com/")


@responses.activate
def test_too_many_redirects(settings):
    fetcher = Fetcher(
        dataclasses.replace(settings, max_redirects=2),
        host_check=lambda _h: None,
        sleeper=lambda _s: None,
    )
    responses.get(
        "https://example.com/loop",
        status=302,
        headers={"Location": "https://example.com/loop"},
    )
    with pytest.raises(FetchError, match="too many redirects"):
        fetcher.fetch("https://example.com/loop")


# --- Credentials must not follow a redirect off-origin ----------------------
#
# Redirects are followed by hand, so `requests` never runs `Session.rebuild_auth`
# — the thing that normally strips `Authorization` when a hop changes origin.
# A crawled site that 302s to a host it controls would otherwise be handed the
# bearer token and session cookie.


def _auth_settings(settings):
    from politecrawl.config import Secret

    return dataclasses.replace(
        settings, auth_token=Secret("s3cret-token"), cookie=Secret("session=abc")
    )


@responses.activate
def test_credentials_are_withheld_after_a_cross_origin_redirect(settings):
    responses.get(
        "https://example.com/",
        status=302,
        headers={"Location": "https://attacker.example/collect"},
    )
    responses.get(
        "https://attacker.example/collect",
        body="<html>ok</html>",
        status=200,
        content_type="text/html",
    )

    fetcher = Fetcher(
        _auth_settings(settings), host_check=lambda _h: None, sleeper=lambda _s: None
    )
    fetcher.fetch("https://example.com/")

    first, second = responses.calls[0].request, responses.calls[1].request
    assert first.headers.get("Authorization") == "Bearer s3cret-token"
    assert first.headers.get("Cookie") == "session=abc"
    # The attacker-controlled hop must see neither.
    assert second.headers.get("Authorization") is None
    assert second.headers.get("Cookie") is None


@responses.activate
def test_credentials_survive_a_same_origin_redirect(settings):
    responses.get(
        "https://example.com/a",
        status=302,
        headers={"Location": "https://example.com/b"},
    )
    responses.get(
        "https://example.com/b",
        body="<html>ok</html>",
        status=200,
        content_type="text/html",
    )

    fetcher = Fetcher(
        _auth_settings(settings), host_check=lambda _h: None, sleeper=lambda _s: None
    )
    fetcher.fetch("https://example.com/a")

    second = responses.calls[1].request
    assert second.headers.get("Authorization") == "Bearer s3cret-token"
