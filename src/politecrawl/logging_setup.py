"""Logging configuration with credential and control-character scrubbing."""

from __future__ import annotations

import logging
import re

_LEVELS = [logging.WARNING, logging.INFO, logging.DEBUG]
_CRED = re.compile(
    r"(?i)(?:authorization|cookie|set-cookie|token)\s*[:=]\s*(?:bearer\s+)?\S+"
    r"|bearer\s+\S+"
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitize_for_log(value: str, max_len: int = 300) -> str:
    """Neutralize untrusted text (URLs, titles) before logging."""
    value = value.replace("\r", "\\r").replace("\n", "\\n")
    value = _CONTROL.sub("?", value)
    return value if len(value) <= max_len else value[:max_len] + "..."


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            if secret in message:
                message = message.replace(secret, "***REDACTED***")
        message = _CRED.sub("***REDACTED***", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(verbosity: int = 0, secrets: list[str] | None = None) -> None:
    level = _LEVELS[min(verbosity, len(_LEVELS) - 1)]
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    handler = logging.StreamHandler()  # stderr
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    )
    handler.addFilter(RedactingFilter(secrets or []))
    root.addHandler(handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
