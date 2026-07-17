"""Command-line interface.

Exit codes:
    0  success
    1  crawl produced no pages / runtime failure
    2  usage / configuration / validation error
    3  security violation (e.g. the seed resolves to a private address)
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import Settings
from .crawler import Crawler
from .errors import (
    ConfigError,
    PolitecrawlError,
    SecurityError,
    ValidationError,
)
from .logging_setup import configure_logging
from .storage import write_jsonl

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_EMPTY = 1
EXIT_USAGE = 2
EXIT_SECURITY = 3


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="politecrawl",
        description="A courteous, safety-first web crawler.",
    )
    parser.add_argument(
        "--version", action="version", version=f"politecrawl {__version__}"
    )
    parser.add_argument("seed", help="the seed URL to start crawling from")
    parser.add_argument(
        "-o", "--output", type=Path, help="write results as JSONL to this path"
    )
    parser.add_argument(
        "--max-pages", type=_positive_int, default=50, help="page cap (default 50)"
    )
    parser.add_argument(
        "--max-depth", type=_positive_int, default=3, help="link depth (default 3)"
    )
    parser.add_argument(
        "--delay",
        type=_non_negative_float,
        default=1.0,
        help="minimum seconds between requests to one host (default 1.0)",
    )
    parser.add_argument(
        "--allow-subdomains",
        action="store_true",
        help="also crawl subdomains of the seed host",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v info, -vv debug"
    )
    parser.set_defaults(func=_cmd_crawl)
    return parser


def _cmd_crawl(args: argparse.Namespace) -> int:
    settings = Settings.from_env(
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        default_delay=args.delay,
        allow_subdomains=args.allow_subdomains,
    )
    with Crawler(settings) as crawler:
        pages, stats = crawler.crawl(args.seed)

    if args.output:
        write_jsonl(pages, args.output)
    else:
        for page in pages:
            print(f"{page.status}  d{page.depth}  {page.url}  {page.title!r}")

    print(
        f"\nfetched={stats.fetched} errors={stats.errors} "
        f"robots_skipped={stats.skipped_robots} "
        f"offsite_skipped={stats.skipped_offsite} "
        f"security_blocked={stats.blocked_security}",
        file=sys.stderr,
    )
    return EXIT_OK if pages else EXIT_EMPTY


def _collect_secrets() -> list[str]:
    secrets: list[str] = []
    try:
        settings = Settings.from_env()
    except ConfigError:
        return secrets
    if settings.auth_token is not None:
        secrets.append(settings.auth_token.reveal())
    if settings.cookie is not None:
        secrets.append(settings.cookie.reveal())
    return secrets


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose, secrets=_collect_secrets())

    try:
        return int(args.func(args))
    except SecurityError as exc:
        logger.error("security violation: %s", exc)
        return EXIT_SECURITY
    except (ConfigError, ValidationError) as exc:
        logger.error("%s", exc)
        return EXIT_USAGE
    except PolitecrawlError as exc:
        logger.error("%s", exc)
        return EXIT_EMPTY
    except KeyboardInterrupt:
        logger.warning("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
