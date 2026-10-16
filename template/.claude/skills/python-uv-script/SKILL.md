---
name: python-uv-script
description: >-
  Single-file tools run by `uv run` with PEP 723 inline metadata — the header (requires-python,
  dependencies, exclude-newer), where a script lives in this project, how it is tested and
  type-checked, and why its dependencies are declared twice. Use when writing a one-file tool, a
  helper that must run before or without the project's venv, a script to run from a URL, or when
  asked for a "uv script", "PEP 723" or "inline script metadata". Defers to python-cli for
  interface conventions.
---

# uv scripts

A uv script is one `.py` file that runs wherever `uv` is: `uv run scripts/<name>.py` reads the
header at the top, builds the script's own environment and runs it, with no project around it.
That is what it is for — a helper that runs before the project's venv exists, a tool handed to
another repo, a file run from a URL. Anything of more than one module, or a command of the
product, is a command in the package instead. Interface rules — exit codes, the stdout/stderr
split — are **python-cli**; everything in `CLAUDE.md` applies under `scripts/` as it does under
`src/`.

## Recipe: add a script

Copy the worked script and its test rather than starting from a blank file:

```bash
mkdir -p scripts tests
cp .claude/skills/python-uv-script/reference/yaml_to_json.py scripts/<name>.py
cp .claude/skills/python-uv-script/reference/test_yaml_to_json.py tests/test_<name>.py
uv add --dev pyyaml                        # what its header already declares
```

They pass the gate and their tests exactly as copied (a generation test proves it). Then:

1. **Rename** `yaml_to_json` to `<name>` in the test's import and its `SCRIPT` path, and replace
   the functions with yours, keeping the shape: the pieces as plain functions with every
   dependency a parameter, `main(argv) -> int`, the `__main__` block.
2. **Declare each dependency twice**, by command, never by editing text:

   ```bash
   uv add --script scripts/<name>.py <dep>   # the header: what `uv run scripts/<name>.py` installs
   uv add --dev <dep>                        # the project venv: what pytest, ty and the debugger see
   ```

   A script that does not read YAML drops `pyyaml` the same way: `uv remove --script` and
   `uv remove --dev`.
3. **Test** the pieces, then `main` through `capsys`, and keep the one smoke test (below).
4. **Check:** `uv run pytest`, then `prek run --all-files`.

## The header

The first thing in the file, above the docstring. `uv add --script` edits a leading block in
place; given a block placed lower it adds a second one at the top, and two blocks is an error.

```python
# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
#
# [tool.uv]
# exclude-newer = "2026-10-16T00:00:00Z"
# ///
```

All three fields, always:

- **`requires-python`** is the project's own floor, `requires-python` in `pyproject.toml`. ruff
  rewrites syntax up to the project's `target-version` and ty checks a script at its *header's*
  version, so a lower floor fails `ty` the first time ruff touches the file.
- **`dependencies`**, even `[]`: uv's docs require it, and an empty list says deliberately that
  the script needs nothing.
- **`exclude-newer`**, a full RFC 3339 timestamp: uv resolves as if nothing newer existed, so the
  script runs the same months later on another machine. Moving the date forward *is* the
  upgrade. Not `uv lock --script`: the `uv-lock` hook never refreshes a `<name>.py.lock`, so it
  would go stale unnoticed; reach for it only when a script is deployed somewhere stable.

No shebang. `#!/usr/bin/env -S uv run --script` is inert on Windows and needs an executable bit
that writing the file never sets, so it documents a `./scripts/<name>.py` that does not work. The
invocation is `uv run scripts/<name>.py` everywhere.

## Two environments

| Command | Environment | Dependencies from |
|---|---|---|
| `uv run scripts/<name>.py` | the script's own, cached by uv | the header |
| `uv run python scripts/<name>.py`, `uv run pytest`, the gate's `ty`, the debugger | the project venv | the dev group |

That is why each dependency is declared twice, and why a mismatch is invisible from inside the
project: the venv has everything. The smoke test in the reference is what catches it —
`uv run --exact scripts/<name>.py --help` in a subprocess. `--exact` matters: a script's
environment keeps what an earlier header installed, so without it a dependency dropped from the
header still imports.

## Shape

- `main(argv: list[str] | None = None) -> int`, `argparse`, and `sys.exit(main())` under the
  `__main__` guard: the **python-cli** contract. `missing-main-guard` and `T20` apply under
  `scripts/` as everywhere — no `print`; data through `sys.stdout.write`.
- Diagnostics through stdlib `logging` on stderr, configured in `main` with
  `logging.basicConfig(..., stream=sys.stderr, force=True)`. Without `force`, the second call in a
  process is a no-op, so every test after the first captures nothing.
- A script that calls an API builds its client in a `build_client` function of its own — the
  conventions hook requires that name — and its tests pass a `httpx.MockTransport` client in.
- One responsibility, one file. A second module means it is no longer a script.

## Testing

`tests/test_<name>.py` imports the script as `from scripts.<name> import main, ...`: the project
root is on pytest's `pythonpath` and is first-party to ty, so a script's functions are called
with literal arguments, as a debugger would. No subprocess and no network — except the one smoke
test, which proves what no import can (its `# noqa: S603` says so). The test file never gets a
header of its own: it runs in the project venv, like every other test.
