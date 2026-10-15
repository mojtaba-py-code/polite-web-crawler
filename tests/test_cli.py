"""CLI tests and credential-redaction check."""

from __future__ import annotations

import json
import logging

import responses

import politecrawl.cli as cli
from politecrawl.errors import SecurityError
from politecrawl.logging_setup import RedactingFilter


@responses.activate
def test_crawl_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("POLITECRAWL_USER_AGENT", "test-agent/1.0 (+contact)")
    # Bypass DNS by making the crawler's fetcher accept any host.
    monkeypatch.setattr("politecrawl.fetcher.ensure_public_host", lambda _h: None)

    responses.get("https://example.com/robots.txt", status=404)
    responses.get(
        "https://example.com/",
        body="<html><title>Home</title><a href='/a'>a</a></html>",
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://example.com/a",
        body="<html><title>A</title></html>",
        status=200,
        content_type="text/html",
    )

    out = tmp_path / "out.jsonl"
    code = cli.main(
        ["https://example.com/", "-o", str(out), "--delay", "0", "--max-pages", "5"]
    )
    assert code == 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    titles = {json.loads(x)["title"] for x in lines}
    assert titles == {"Home", "A"}


@responses.activate
def test_blocked_seed_is_security_exit(capsys):
    # A literal private IP needs no DNS lookup, and the guard refuses it before
    # any request is made (responses would fail an unmocked one).
    code = cli.main(["http://192.168.1.1/", "--delay", "0"])
    assert code == cli.EXIT_SECURITY
    assert "security_blocked=1" in capsys.readouterr().err


@responses.activate
def test_blocked_link_after_a_fetched_seed_is_not_a_security_exit(monkeypatch):
    # Blocking one discovered link must not turn a successful crawl into exit 3.
    def guard(host):
        if host == "internal.example.com":
            raise SecurityError("refusing non-public address 10.0.0.1")

    monkeypatch.setattr("politecrawl.fetcher.ensure_public_host", guard)
    responses.get("https://example.com/robots.txt", status=404)
    responses.get(
        "https://example.com/",
        body="<html><a href='https://internal.example.com/'>x</a></html>",
        status=200,
        content_type="text/html",
    )

    code = cli.main(["https://example.com/", "--delay", "0", "--allow-subdomains"])
    assert code == cli.EXIT_OK


@responses.activate
def test_unreachable_seed_is_empty_exit(monkeypatch):
    # A seed that fails for a non-security reason stays exit 1.
    monkeypatch.setattr("politecrawl.fetcher.ensure_public_host", lambda _h: None)
    responses.get("https://example.com/robots.txt", status=404)
    responses.get("https://example.com/", status=404)

    code = cli.main(["https://example.com/", "--delay", "0"])
    assert code == cli.EXIT_EMPTY


def test_bad_max_pages_is_usage_error():
    # argparse rejects a non-positive int -> SystemExit(2).
    try:
        cli.main(["https://example.com/", "--max-pages", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit")


def test_credential_is_redacted_in_logs():
    f = RedactingFilter(["super-secret-cookie"])
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1,
        "sending Cookie: super-secret-cookie", None, None,
    )
    f.filter(rec)
    assert "super-secret-cookie" not in rec.getMessage()
