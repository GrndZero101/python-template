# TODO

Outstanding work, with enough context to pick up cold in a new session.
Rules and workflow live in [CLAUDE.md](CLAUDE.md); this file is only what is *not yet done*.

## Status snapshot

- The repo **is** a working copier template. `copier.yml` at the root, everything that becomes a
  generated project under `template/` via `_subdirectory`. All five project types
  (`cli-modern`, `cli-stdlib`, `fastapi`, `tui`, `data`) generate, pass their own gate and pass
  their own tests.
- Toolchain: `uv`, `ruff`, `ty`, `prek`, `rumdl`, `copier` 9.17.0. Four modules under
  `template/tools/`: `check_nested_defs` (no linter covers `def` inside `def`), `branch_guard` and
  `gate` (the two hooks), and `hook_payload` (shared parsing so they cannot diverge).
- Guards live: `PreToolUse` blocks edits to *repo* files on `main`, `no-commit-to-branch` blocks
  direct commits while still permitting `--no-ff` merges, `conventional-pre-commit` checks every
  message, `SessionStart` reports branch and tree state. Every hook is a single executable
  invocation, no shell operators.
- Only five files under `template/` are `.jinja`: `pyproject.toml`, `README.md`,
  `.pre-commit-config.yaml`, `.copier-answers.yml`, and the two example test modules. The six
  source modules ship literally because their internal imports are **relative** — nothing inside
  `src/` names the package, so copier renders only the directory name.
- `template/` cannot be linted in place (Jinja, no `pyproject.toml`). `tests/test_template.py` is
  the only thing that verifies it: 25 tests that generate a project per type and run that
  project's gate and suite inside it. It is wired into the gate and costs about a minute.
- `mcp-debugger` is installed and **proven** against `geo`. Node LTS 24.18.0 via winget,
  `@debugmcp/mcp-debugger` 0.23.0 global, `debugpy` a dev dependency, server registered at
  **user scope** so nothing ships yet. It confirmed CLAUDE.md's central claim empirically: a
  module-level helper was called from a breakpoint with invented literal arguments
  (`render_places_json([Place.model_validate({...})])`), which a nested `def` makes impossible.

## Do next

### 1. Non-`cli-modern` types generate an empty package

`fastapi`, `tui`, `data` and `cli-stdlib` receive the infrastructure — `tools/`, `CLAUDE.md`, the
gate, the hooks, their one skill — but `src/<package>/` contains only `__init__.py` and `py.typed`.
That is honest (the `geo`/`currency` demo is a typer demonstration and would drag typer, httpx and
rich into an unrelated stack) but it gives those projects nothing to pattern-match against.

Each needs a small example in its own idiom: a FastAPI app with one router and an `ASGITransport`
test, a Textual app with a Pilot test, a polars/duckdb pipeline, an argparse CLI. The skills already
describe the conventions; this is about shipping one worked instance of each.

Note `logging_setup.py` is currently excluded from those types because it imports `loguru`. A
stdlib `logging` equivalent is probably the right shared default, with the loguru one shipping only
where a skill calls for it.

### 2. Publish and test the remote path

Everything so far is verified against a **local** template path. Untested:

- `copier copy gh:GrndZero101/python-template <dest>` from an actual remote.
- `copier update` on a generated project — the machinery is in place (`.copier-answers.yml` ships,
  the generation tasks leave a clean tree and an initial commit) but no update has been run.
  `pytest-copie` exposes `.update()` for this.
- `_src_path` currently records the local filesystem path in generated projects.

Copier resolves a local template from the **working tree**, warning `DirtyLocalWarning`, which is
why the generation tests validate uncommitted work. A remote template resolves from a tag or
branch instead, so version pinning only starts mattering once this is published.

### 3. Verify generation into unusual git states

Listed earlier and still unverified:

- A destination directory that is already a git repo, and one whose default branch is not `main`
  (`branch_guard` takes `--protected main master`).
- The generation tasks assume `git init -b main` succeeds, i.e. that nothing is there yet.

### 4. Decide whether `mcp-debugger` ships

Still user-scope only, deliberately: project scope would force **Node 22+ onto every generated
Python project**. `debugpy` is already a dev dependency, so the Python half travels regardless.

## Nice to have

- **Commit summary length is unenforced.** `conventional-pre-commit` validates format but not the
  72-character rule. A custom `commit-msg` check could close it, but the bar is still "prove no
  native tool does it first".
- **The merge-subject convention is unenforceable by the current checker.**
  `conventional-pre-commit` exempts any message beginning with `Merge`, so git's default subject
  passes. Documented in `template/CLAUDE.md`; only `/code-review` catches a violation.
- **Gate instrumentation.** Append pass/fail from the `PostToolUse` hook to a gitignored
  `.gate.log` for a hard count of how often the gate catches something.
- **The generation tests are not offline.** `uv sync` runs during generation and reaches the
  network on a cold cache. Everything else about them is deterministic.
