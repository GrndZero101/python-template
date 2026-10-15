# typer CLI rules

What this project's stack adds to the Python rules in `CLAUDE.md`. They are loaded with it, at the
same priority, and the same gate enforces them. How to do each thing is in the **python-cli-typer**
skill; this file is only what must hold.

## Patches

The sanctioned patches. A command's end-to-end test through `main` replaces `<module>.build_client`,
or a TUI command's `<module>.run_screen`, with `monkeypatch.setattr` — the one thing each command
builds rather than takes as a parameter. Patch nothing else.

## What is mechanically enforced

| Rule | Enforced by |
|---|---|
| An HTTP client comes from `build_client`, never a bare `httpx.Client()` | `tools/check_conventions.py` `raw-httpx-client` |
| Tests replace the network with `httpx.MockTransport`, never by patching httpx | `tools/check_conventions.py` `patched-httpx` |
| typer parameters use `Annotated`, never `= typer.Option(...)` | `tools/check_conventions.py` `typer-default` |
