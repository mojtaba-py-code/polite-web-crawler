# politecrawl

[![CI](https://github.com/mojtaba-py-code/web-scraping/actions/workflows/ci.yml/badge.svg)](https://github.com/mojtaba-py-code/web-scraping/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-black.svg)](https://github.com/astral-sh/ruff)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A courteous, safety-first web crawler and scraper. Given a seed URL it crawls
within that site, extracts structured data from each page, and writes JSON
Lines — while respecting `robots.txt` and rate limits and defending against
the security pitfalls that scrapers routinely fall into (SSRF, oversized
responses, redirect abuse, credential leakage).

It is built as a realistic example of a well-structured, security-conscious
scraping project. See `SECURITY.md` for the full threat model.

## Install

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

This exposes a `politecrawl` command; you can also run `python -m politecrawl`.

## Configuration

Set an honest, contactable User-Agent so site owners can reach you:

```bash
export POLITECRAWL_USER_AGENT="mybot/1.0 (+https://me.example/bot; me@example.com)"
```

For scraping pages behind a login, provide credentials via the environment
only (never the command line); they are redacted from logs:

```bash
export POLITECRAWL_AUTH_TOKEN="..."      # sent as: Authorization: Bearer ...
export POLITECRAWL_COOKIE="session=..."  # sent as: Cookie: ...
```

## Usage

```bash
# Crawl a site (default: same host, depth 3, 50 pages, 1s per-host delay):
politecrawl https://example.com/ -v

# Bound the crawl and save results:
politecrawl https://example.com/ \
    --max-pages 100 --max-depth 2 --delay 1.5 \
    -o output/example.jsonl

# Include subdomains:
politecrawl https://example.com/ --allow-subdomains
```

Console output (one line per page) looks like:

```text
200  d0  https://example.com/          'Example Domain'
200  d1  https://example.com/about     'About Us'
```

Each JSONL record contains: `url`, `status`, `depth`, `title`, `description`,
`headings`, `link_count`, `content_hash`, and `fetched_at`.

### Exit codes

| Code | Meaning                                     |
|------|---------------------------------------------|
| 0    | success (at least one page scraped)         |
| 1    | no pages scraped / runtime failure          |
| 2    | usage / configuration / validation error    |
| 3    | security violation (e.g. private seed host) |

## Use as a library

```python
from politecrawl import Crawler, Settings

with Crawler(Settings.from_env(max_pages=20)) as crawler:
    pages, stats = crawler.crawl("https://example.com/")
    for page in pages:
        print(page.url, page.title)
    print(stats.to_dict())
```

## What it does right

Safety. An SSRF guard resolves every host (including redirect targets and
robots.txt) and refuses private/loopback/link-local/reserved addresses;
redirects are followed manually and re-validated per hop; responses are
size-capped and content-type-checked; only http/https URLs are ever fetched.

Etiquette. robots.txt is fetched, cached, and obeyed (failing closed if it
cannot be read); `Crawl-delay` is honored; a per-host rate limiter spaces
requests; the crawler identifies itself and stays on-site by default; work
is bounded by page and depth limits.

Engineering. Small, single-purpose modules; full type hints; frozen
dataclasses; a typed error hierarchy; a single failing page never aborts the
crawl; and a test suite that mocks HTTP and fakes DNS so nothing touches the
network.

## Project layout

```text
politecrawl/
├── pyproject.toml          # metadata, deps, entry point, ruff/mypy/bandit
├── README.md
├── SECURITY.md             # threat model + etiquette
├── .env.example
├── src/politecrawl/
│   ├── __init__.py
│   ├── __main__.py         # python -m politecrawl
│   ├── cli.py              # argparse, output, exit codes
│   ├── crawler.py          # bounded BFS crawl loop
│   ├── fetcher.py          # safe GET: SSRF, redirects, size cap, retries
│   ├── robots.py           # robots.txt fetch/cache/obey + crawl-delay
│   ├── ratelimit.py        # per-host politeness throttle
│   ├── parser.py           # BeautifulSoup extraction + link filtering
│   ├── urls.py             # validation, normalization, scope, SSRF guard
│   ├── storage.py          # atomic JSONL writer
│   ├── config.py           # env-based Settings + Secret wrapper
│   ├── logging_setup.py    # logging + redaction / log-injection defense
│   ├── models.py           # Page / CrawlStats dataclasses
│   └── errors.py           # exception hierarchy
└── tests/                  # urls/SSRF, robots, parser, fetcher, crawler, cli
```

## Development

```bash
pytest              # mocked HTTP, faked DNS; no network
ruff check .        # lint incl. security (S) rules
mypy src            # strict type-checking
bandit -r src       # static security analysis
```

## Legal note

Only crawl sites you are authorized to crawl, and respect each site's Terms
of Service and applicable law. The technical controls here enforce good
behavior; they do not grant permission.

## License

MIT.
