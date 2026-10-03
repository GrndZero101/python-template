# Logging with loguru

The three things loguru needs in this stack, and how to assert on log output in a test.

loguru replaces stdlib `logging` rather than configuring it, so ruff's `LOG`/`G` rules stop applying
to loguru call sites. CLAUDE.md permits it for this stack; in exchange, all three of these are
mandatory.

1. **Route stdlib logging into it.** Your dependencies — httpx, SDKs — still use `logging`, and
   without an `InterceptHandler` their output vanishes. Put the canonical handler in its own
   `logging_setup.py` and call it once from `main`. It is vendored boilerplate with a frame-walking
   loop; it is not an example of house style. It holds `httpcore` at INFO, because that library's
   DEBUG is a wire trace of some twenty lines per request; add any other such library to
   `CHATTY_LOGGERS` rather than lowering the whole threshold.
2. **`caplog` does not work.** loguru does not propagate to pytest's handlers, so log assertions
   silently pass against empty text. Add the documented `propagate_logs` autouse fixture to
   `conftest.py`, or assert through a `logger.add(records.append)` sink.

   **Through `main`, assert on captured stderr instead.** The app callback calls
   `configure_logging`, which removes every sink — including one a test added beforehand — and
   then adds one on `sys.stderr`, which by then is pytest's capture. So
   `assert "could not reach" in capsys.readouterr().err` works, and a pre-added sink silently
   receives nothing. Keep the sink approach for calling a plain function directly.
3. **`logger.catch(reraise=True)`, always.** A bare `logger.catch` swallows the exception — the same
   defect as `except: pass`.

loguru's default sink is already `stderr`; never move it to stdout.
