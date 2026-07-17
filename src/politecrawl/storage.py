"""Persist crawl results as JSON Lines, written atomically."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path

from .models import Page

logger = logging.getLogger(__name__)


def write_jsonl(pages: list[Page], path: str | Path) -> None:
    """Write one JSON object per page, atomically replacing *path*."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(p.to_dict(), ensure_ascii=False) + "\n" for p in pages)
    _atomic_write(path, text)
    logger.info("wrote %d page(s) to %s", len(pages), path)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            Path(tmp).unlink()
        raise
