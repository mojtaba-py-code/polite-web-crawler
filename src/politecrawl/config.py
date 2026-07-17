"""Runtime settings, sourced from the environment with validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .errors import ConfigError

DEFAULT_USER_AGENT = (
    "politecrawl/1.0 (+https://example.com/bot; contact@example.com)"
)
# Only these content types are parsed; anything else is skipped.
DEFAULT_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


class Secret:
    """Wraps a credential so it never appears in logs or reprs."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable crawler configuration."""

    user_agent: str = DEFAULT_USER_AGENT
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    default_delay: float = 1.0  # seconds between requests to one host
    max_pages: int = 50
    max_depth: int = 3
    max_bytes: int = 5 * 1024 * 1024  # 5 MiB response cap
    max_redirects: int = 5
    max_retries: int = 2
    backoff_base: float = 0.5
    allow_subdomains: bool = False
    content_types: tuple[str, ...] = DEFAULT_CONTENT_TYPES
    auth_token: Secret | None = field(default=None)
    cookie: Secret | None = field(default=None)

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.connect_timeout, self.read_timeout)

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        ua = os.environ.get("POLITECRAWL_USER_AGENT", DEFAULT_USER_AGENT).strip()
        if not ua:
            raise ConfigError("user agent must not be empty")

        token = os.environ.get("POLITECRAWL_AUTH_TOKEN")
        cookie = os.environ.get("POLITECRAWL_COOKIE")

        base: dict[str, object] = {
            "user_agent": ua,
            "auth_token": Secret(token) if token else None,
            "cookie": Secret(cookie) if cookie else None,
        }
        base.update(overrides)
        settings = cls(**base)  # type: ignore[arg-type]
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.default_delay < 0:
            raise ConfigError("default_delay must be >= 0")
        if self.max_pages <= 0:
            raise ConfigError("max_pages must be > 0")
        if self.max_depth < 0:
            raise ConfigError("max_depth must be >= 0")
        if self.max_bytes <= 0:
            raise ConfigError("max_bytes must be > 0")

    def auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.auth_token is not None:
            headers["Authorization"] = f"Bearer {self.auth_token.reveal()}"
        if self.cookie is not None:
            headers["Cookie"] = self.cookie.reveal()
        return headers
