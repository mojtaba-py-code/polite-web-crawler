# Contributing

Thanks for taking a look. This is how the project is developed locally and what
CI expects before a change lands.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # optional: auth token / cookie / user-agent
```

## Before you push

These are exactly the steps CI runs, so run them locally first:

```bash
ruff check src tests
mypy src                          # strict
pytest
bandit -r src --severity-level medium
```

CI runs the same on Python 3.11 and 3.12.

## Conventions

- **Every outbound URL is validated.** Anything that issues a request — including
  each redirect hop and `robots.txt` — goes through `urls.validate_url` and
  `urls.ensure_public_host`. Never call the network around that path.
- **Fail closed.** If `robots.txt` cannot be read, we decline to fetch. Keep new
  code on the same side of that trade-off.
- **Bounded work.** Responses are size-capped and streamed; crawls are bounded by
  `max_pages` / `max_depth`. New loops need a bound too.
- **Secrets.** Credentials come from the environment, live in the `Secret`
  wrapper, and never reach a log line. Untrusted strings go through
  `sanitize_for_log` before logging.
- **Typing.** `src/` is fully typed; `mypy` strict must stay clean.
- **Tests.** Add tests with the change; network calls are mocked, never real.
- **Commits.** Short imperative subject; the body explains *why*.

The reasoning behind these rules is written up in [SECURITY.md](SECURITY.md) —
read it before changing anything in the fetch or URL-handling path.
