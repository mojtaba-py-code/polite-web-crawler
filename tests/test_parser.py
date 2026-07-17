"""HTML extraction and link-filtering tests."""

from __future__ import annotations

from politecrawl.parser import parse_html

HTML = b"""
<html>
  <head>
    <title>  Hello   World </title>
    <meta name="description" content="A test page.">
  </head>
  <body>
    <h1>Main Heading</h1>
    <h2>Sub</h2>
    <a href="/about">About</a>
    <a href="https://example.com/contact">Contact</a>
    <a href="mailto:a@b.com">Email</a>
    <a href="javascript:void(0)">JS</a>
    <a href="/about#team">About team (dup after defrag)</a>
  </body>
</html>
"""


def test_extracts_title_and_description():
    out = parse_html("https://example.com/", HTML)
    assert out.title == "Hello World"  # whitespace collapsed
    assert out.description == "A test page."


def test_extracts_headings():
    out = parse_html("https://example.com/", HTML)
    assert out.headings == ["Main Heading", "Sub"]


def test_links_resolved_filtered_and_deduped():
    out = parse_html("https://example.com/", HTML)
    # mailto/javascript dropped; /about and /about#team dedupe to one.
    assert "https://example.com/about" in out.links
    assert "https://example.com/contact" in out.links
    assert all(link.startswith("https://") for link in out.links)
    assert out.links.count("https://example.com/about") == 1


def test_content_hash_is_stable():
    a = parse_html("https://example.com/", HTML)
    b = parse_html("https://example.com/", HTML)
    assert a.content_hash == b.content_hash
    assert len(a.content_hash) == 64
