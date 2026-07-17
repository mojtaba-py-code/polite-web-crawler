"""HTML parsing and link extraction.

Uses BeautifulSoup with the stdlib ``html.parser`` (no native dependencies).
Never uses regular expressions to parse HTML. Extracted links are resolved
to absolute URLs, validated, normalized, and de-duplicated; anything that is
not http/https is dropped.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

from .errors import ValidationError
from .urls import normalize_url, validate_url

logger = logging.getLogger(__name__)

_MAX_HEADINGS = 20
_MAX_LINKS = 2000


@dataclass(frozen=True, slots=True)
class Extracted:
    title: str
    description: str
    headings: list[str]
    links: list[str]
    content_hash: str


def parse_html(base_url: str, body: bytes) -> Extracted:
    """Extract structured fields and outbound links from an HTML page."""
    soup = BeautifulSoup(body, "html.parser")

    title = _clean(soup.title.string) if soup.title and soup.title.string else ""

    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta is not None:
        content = meta.get("content")
        if isinstance(content, str):
            description = _clean(content)

    headings = [
        _clean(h.get_text())
        for h in soup.find_all(["h1", "h2"])[:_MAX_HEADINGS]
        if h.get_text(strip=True)
    ]

    links = _extract_links(base_url, soup)
    digest = hashlib.sha256(body).hexdigest()

    return Extracted(
        title=title,
        description=description,
        headings=headings,
        links=links,
        content_hash=digest,
    )


def _extract_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not isinstance(href, str):
            continue
        absolute, _frag = urldefrag(urljoin(base_url, href.strip()))
        try:
            validate_url(absolute)
        except ValidationError:
            continue  # skip mailto:, javascript:, tel:, malformed, etc.
        canonical = normalize_url(absolute)
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
        if len(out) >= _MAX_LINKS:
            break
    return out


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())
