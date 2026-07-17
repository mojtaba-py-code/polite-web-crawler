# Security and etiquette design

A crawler acts on URLs it does not control, so it must treat every link and
every response as untrusted. This document lists the controls and the
crawling etiquette politecrawl follows.

## Threat model

- A page under a target site (or an attacker-influenced page) supplies a
  link that points the crawler at an internal service or cloud metadata
  endpoint (SSRF).
- A server returns a huge or endless response to exhaust memory/disk.
- A redirect chain ends at an internal address.
- Credentials used for authenticated scraping leak into logs or output.
- The crawler misbehaves toward a site (ignoring robots.txt, hammering it).

## Controls

SSRF prevention (`urls.ensure_public_host`). Before every request — including
each redirect hop and robots.txt — the target host is resolved and rejected
unless *all* of its addresses are public. Private, loopback, link-local
(including `169.254.169.254`), reserved, multicast, and unspecified ranges
are refused. Residual risk: DNS rebinding between the check and the actual
connection; for higher assurance, pin the resolved IP and connect to it
directly. This is documented rather than silently ignored.

Manual redirect validation (`fetcher`). Redirects are not auto-followed by
requests; each `Location` is resolved, re-validated (scheme, host), and
re-checked for SSRF before the next request, with a hard hop limit.

Response-size cap. Responses are streamed and aborted once `max_bytes` is
exceeded (and rejected up front if `Content-Length` already exceeds it),
defeating huge-response and decompression-style bombs.

Content-type allowlist. Only `text/html` / `application/xhtml+xml` bodies are
parsed; other types are skipped.

Input validation (`urls.validate_url`). Only `http`/`https` schemes are
accepted; URLs with embedded credentials or absurd length are rejected;
links that are not http/https (mailto, javascript, tel) are dropped.

Secret handling. Optional auth token / cookie come only from the environment
(`POLITECRAWL_AUTH_TOKEN`, `POLITECRAWL_COOKIE`), are wrapped in a `Secret`
type with a masked repr, sent only as request headers, and scrubbed from
logs by a redaction filter (which also matches `Authorization`/`Cookie`
patterns). TLS verification is left at the secure default.

Log-injection defense. Untrusted strings (URLs, titles) pass through
`sanitize_for_log`, which strips control characters and escapes newlines
before they reach a log line.

Robustness. Explicit timeouts on every request; retries with backoff and
jitter on timeouts, connection errors, and 5xx; a single failing page is
logged and skipped rather than aborting the crawl.

## Crawling etiquette

- robots.txt is fetched, cached, and obeyed for our User-Agent. If it cannot
  be read (network/5xx), the crawler declines to fetch — it fails closed.
- The site's `Crawl-delay` is honored; the effective delay is the larger of
  it and the configured `--delay`.
- Requests to one host are spaced by a per-host rate limiter.
- The crawler identifies itself with an honest, contactable User-Agent
  (set `POLITECRAWL_USER_AGENT`), and stays within the seed's site by
  default.
- Work is bounded by `max_pages` and `max_depth` so a crawl always ends.

## Operator responsibilities

- Only crawl sites you are authorized to crawl; respect each site's Terms of
  Service and applicable law. Technical controls do not grant permission.
- Set a real contact in the User-Agent.
- Run `bandit -r src` and `pip-audit` in CI (dev dependencies included).
