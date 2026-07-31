# python-template

A Python project template built around one idea: every rule in [CLAUDE.md](CLAUDE.md) exists so a
human (or an AI agent) can stop the program and inspect it. Structure, debuggability, and
portability rules are mechanically enforced by lint config and a `prek` gate — not just documented
and hoped for.

## What's here

- **`src/python_template/`** — a demo CLI (`cli`) with two subcommands, `geo` and `currency`, on the
  typer/httpx/pydantic/rich/loguru stack. Offline-tested via `httpx.MockTransport`.
- **`tools/`** — the custom checks no off-the-shelf linter covers: `check_nested_defs.py` (no
  `def` inside a `def`), `branch_guard.py` and `gate.py` (the `PreToolUse`/`PostToolUse` hooks that
  block edits to `main` and run the lint gate on save), and `hook_payload.py` (shared parsing).
- **`.claude/skills/`** — stack-specific conventions (`python-cli`, `python-cli-stdlib`,
  `python-cli-modern`, `python-fastapi`, `python-tui`, `python-data`) that an agent loads based on
  what the project actually depends on.
- **`CLAUDE.md`** — the full rule set: structure, debuggability, agent-friendliness, portability,
  branching, and commit conventions, plus a table of exactly what is enforced by what.

## Setup

```bash
uv sync
prek install && prek install -t commit-msg && prek install -t pre-merge-commit
```

All three shims are required — `prek install` alone wires only `pre-commit`, which silently skips
the commit-message check and breaks `--no-ff` merges into `main`.

## Commands

```bash
ruff format . && ruff check --fix .              # format, then auto-fix
ty check                                         # types
rumdl fmt . && rumdl check .                     # markdown
uv run pytest                                    # tests
uv run python tools/check_nested_defs.py src tests tools
prek run --all-files                             # everything above, as one gate
```

## License

[MIT](LICENSE)
