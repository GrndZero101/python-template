# httpx

**Start from `http_client.py` in this directory** rather than building a client yourself: it is
tested, and sets per-phase timeouts, a User-Agent, status retries honouring `Retry-After`, proxies
from the environment, and debug logging. `status.py` shows a command using it. What follows is
why, and how to test code that takes a client.

```python
def fetch_records(client: httpx.Client, *, page_size: int = 100) -> Iterator[Record]:
    """Yield records, following pagination."""
```

Sequential and synchronous by default. Reach for `httpx.AsyncClient` only for fan-out, under
**Concurrency** below.

- **Inject the client.** Build it once at the command boundary, pass it down. Tests substitute
  `httpx.MockTransport`; nothing touches the network.
- **Timeouts are per-phase.** `httpx.Timeout(5.0, connect=2.0, read=30.0)` — a single float applies
  one value to all phases, which is rarely what a long-polling API needs.
- **`HTTPTransport(retries=N)` retries connection failures only — not 429 or 5xx.** Nearly
  everyone assumes otherwise. `http_client.py`'s `RetryTransport` adds status retries, honouring
  `Retry-After`, for idempotent methods only.
- **Any `transport=` switches off `HTTPS_PROXY` and `NO_PROXY`.** httpx reads the proxy variables
  only when it builds its own transports, so a client given one silently connects direct — behind
  a corporate proxy, it simply fails. `http_client.py`'s `EnvironmentProxyTransport` reads them
  back; keep it under any transport you add in production.
- **Test through `httpx.MockTransport`**, never the network. A handler is a plain module-level
  function, bound with `functools.partial` rather than a lambda or a nested `def`:

  ```python
  def _respond(status: int, body: str, _request: httpx.Request) -> httpx.Response:
      return httpx.Response(status, text=body)


  def client_returning(body: str, status: int = 200) -> httpx.Client:
      handler = functools.partial(_respond, status, body)
      return httpx.Client(transport=httpx.MockTransport(handler))


  def test_parses_the_body() -> None:
      with client_returning('[{"id": 1}]') as client:
          assert list(fetch_records(client)) == [Record(id=1)]
  ```

  Also assert that a caller-supplied client is **not** closed by the function — it does not own it.

- Pagination is a generator that yields records, not a function returning an accumulated list. The
  caller then streams and a `--limit` can stop early.
- `response.raise_for_status()` at the boundary; let the domain function raise and let `main` decide
  the exit code.
