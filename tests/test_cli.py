"""CLI tests and credential-redaction check."""

from __future__ import annotations

import json
import logging

import responses

import politecrawl.cli as cli
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
