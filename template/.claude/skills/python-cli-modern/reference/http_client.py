"""An httpx client with the defaults every API-calling command needs. Copy, then adjust constants.

    cp .claude/skills/python-cli-modern/reference/http_client.py src/<package>/
    cp .claude/skills/python-cli-modern/reference/test_http_client.py tests/
    uv add httpx

What `build_client` sets up, and why each one:

- **Per-phase timeouts.** A single float applies to connect, read, write and pool alike; a slow
  API wants a long read and a short connect.
- **A descriptive User-Agent**, `<script>/<version>`, so the API's operators can see who is calling.
- **Retry on 429 and 5xx, honouring `Retry-After`.** httpx's own `retries=` covers only failures
  to *connect*, never a status code. Only idempotent methods are retried: repeating a POST that
  the server may already have acted on is not safe.
- **A debug line per request and response**, visible with `-v`, on stderr through loguru.
- **Proxies from the environment**: `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` and `NO_PROXY`, a
  `NO_PROXY` entry exempting its host and every host under it. httpx ignores those variables as soon as a client is given
  its own transport, which this one always is, so `EnvironmentProxyTransport` routes each request
  itself. The Windows registry and macOS system proxy settings are not read.

The client is built by the command and passed down; never keep one at module level. Tests pass
`transport=httpx.MockTransport(...)` and `sleep=` a recorder, so nothing waits or touches the network.
"""

import email.utils
import time
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib import metadata

import httpx
from loguru import logger

from .config import DIST_NAME, PROG_NAME

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 0.5  # doubled after each failed attempt
MAX_DELAY_SECONDS = 30.0  # a Retry-After longer than this is capped, not obeyed
CONNECT_RETRIES = 2  # httpx's own retries, for failures to connect only


def _utc_now() -> datetime:
    """Return the current time. The default clock; tests pass their own."""
    return datetime.now(UTC)


def parse_retry_after(value: str, now: datetime) -> float | None:
    """Return the seconds a `Retry-After` header asks for, or None if it cannot be read.

    The header is either a number of seconds or an HTTP date.
    """
    stripped = value.strip()
    if stripped.isdigit():
        return float(stripped)
    try:
        when = email.utils.parsedate_to_datetime(stripped)
    except TypeError, ValueError:
        logger.debug("ignoring unreadable Retry-After {!r}", value)
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


def retry_delay(response: httpx.Response, attempt: int, now: datetime) -> float:
    """Return how long to wait before the next attempt, preferring the server's `Retry-After`."""
    header = response.headers.get("Retry-After")
    asked = parse_retry_after(header, now) if header is not None else None
    delay = asked if asked is not None else BACKOFF_SECONDS * 2 ** (attempt - 1)
    return min(delay, MAX_DELAY_SECONDS)


class RetryTransport(httpx.BaseTransport):
    """Wraps another transport, repeating idempotent requests that get a retryable status."""

    def __init__(
        self,
        inner: httpx.BaseTransport,
        *,
        attempts: int = MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._inner = inner
        self._attempts = attempts
        self._sleep = sleep
        self._now = now

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send `request`, retrying while the status is retryable and attempts remain."""
        attempt = 1
        response = self._inner.handle_request(request)
        while self._should_retry(request, response, attempt):
            delay = retry_delay(response, attempt, self._now())
            logger.debug(
                "{} {} -> {}; retrying in {:.1f}s",
                request.method,
                request.url,
                response.status_code,
                delay,
            )
            response.close()
            self._sleep(delay)
            attempt += 1
            response = self._inner.handle_request(request)
        return response

    def _should_retry(self, request: httpx.Request, response: httpx.Response, attempt: int) -> bool:
        """Return whether another attempt is both allowed and worthwhile."""
        if attempt >= self._attempts or request.method not in IDEMPOTENT_METHODS:
            return False
        return response.status_code in RETRY_STATUSES

    def close(self) -> None:
        """Close the wrapped transport."""
        self._inner.close()


def bypasses_proxy(host: str, no_proxy: str) -> bool:
    """Return whether `NO_PROXY` exempts `host`: `*`, the host itself, or a domain it is under."""
    host = host.lower()
    for entry in no_proxy.split(","):
        name = entry.strip().lstrip(".").lower()
        if name == "*" or (name and (host == name or host.endswith(f".{name}"))):
            return True
    return False


def proxy_for(url: httpx.URL, proxies: Mapping[str, str]) -> str | None:
    """Return the proxy `proxies` names for `url`, or None to connect directly.

    `proxies` is what `urllib.request.getproxies_environment()` returns: lower-case schemes, plus
    `all` for `ALL_PROXY` and `no` for `NO_PROXY`.
    """
    if bypasses_proxy(url.host, proxies.get("no", "")):
        return None
    proxy = proxies.get(url.scheme) or proxies.get("all")
    if not proxy:
        return None
    return proxy if "://" in proxy else f"http://{proxy}"


class EnvironmentProxyTransport(httpx.BaseTransport):
    """Sends each request directly, or through the proxy the environment names for its URL."""

    def __init__(self, proxies: Mapping[str, str], *, retries: int = CONNECT_RETRIES) -> None:
        self._proxies = proxies
        self._retries = retries
        self._direct = httpx.HTTPTransport(retries=retries)
        self._proxied: dict[str, httpx.HTTPTransport] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send `request` over the connection its URL calls for."""
        proxy = proxy_for(request.url, self._proxies)
        if proxy is None:
            return self._direct.handle_request(request)
        if proxy not in self._proxied:
            self._proxied[proxy] = httpx.HTTPTransport(proxy=proxy, retries=self._retries)
        return self._proxied[proxy].handle_request(request)

    def close(self) -> None:
        """Close the direct transport and every proxy transport opened."""
        self._direct.close()
        for transport in self._proxied.values():
            transport.close()


def _log_request(request: httpx.Request) -> None:
    """Event hook: one debug line per request sent."""
    logger.debug("{} {}", request.method, request.url)


def _log_response(response: httpx.Response) -> None:
    """Event hook: one debug line per response received."""
    logger.debug("{} {} -> {}", response.request.method, response.request.url, response.status_code)


def user_agent(version_of: Callable[[str], str] = metadata.version) -> str:
    """Return `<script>/<version>`, so the API's operators can see who is calling."""
    return f"{PROG_NAME}/{version_of(DIST_NAME)}"


def build_client(
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Client:
    """Return a client with timeouts, a User-Agent, status retries, proxies and debug logging.

    Use it as a context manager at the command boundary and pass it down. `transport` is for
    tests: an `httpx.MockTransport` there means nothing touches the network.
    """
    if transport is None:
        transport = EnvironmentProxyTransport(urllib.request.getproxies_environment())
    return httpx.Client(
        transport=RetryTransport(transport, attempts=attempts, sleep=sleep),
        timeout=timeout,
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [_log_request], "response": [_log_response]},
        follow_redirects=True,
    )
