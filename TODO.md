# TODO

Outstanding work, with enough context to pick up cold in a new session.
Rules and workflow live in [CLAUDE.md](CLAUDE.md); this file is only what is *not yet done*.

## Status snapshot

- The repo **is** a working copier template, and it is **published** at
  [GrndZero101/python-template](https://github.com/GrndZero101/python-template). `copier.yml` at the
  root, everything that becomes a generated project under `template/` via `_subdirectory`. All five
  project types (`cli-modern`, `cli-stdlib`, `fastapi`, `tui`, `data`) generate, pass their own gate
  and pass their own tests.
- The remote route is verified end to end: `copier copy gh:GrndZero101/python-template <dest>`
  generates, and `_src_path` records the `gh:` reference rather than a local path.
- `copier update` works and is covered by tests — a later template change reaches an existing
  project, a file the project edited survives the merge, and the project still passes its gate
  afterwards. Getting there required guarding every `_task` with
  `when: "{{ _copier_operation == 'copy' }}"`; unguarded, the tasks re-ran on update and the
  `git commit` task failed against the project's own `no-commit-to-branch` hook, so **every update
  exited non-zero**. Note the variable is `_copier_operation`, not `_copier_conf.operation` — the
  latter renders undefined, which is falsy, which silently disables every task including on copy.
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
  the only thing that verifies it: 38 tests that generate a project per type and run that project's
  gate and suite inside it. Wired into the gate; costs about a minute.
- `mcp-debugger` is installed and **proven** against `geo`. Node LTS 24.18.0 via winget,
  `@debugmcp/mcp-debugger` 0.23.0 global, `debugpy` a dev dependency, server registered at
  **user scope** so nothing ships yet.

## In flight

### Dogfood in `GrndZero101/template-dogfood`

A private consumer repo, generated from the published template as `cli-modern`, pushed, gate green
and 91 tests passing. The plan is to add a `cli weather <city>` subcommand alongside `geo` and
`currency` and see what the experience is actually like.

**This cannot be driven from a session rooted in `python-template`.** Claude Code loads
`.claude/settings.json` and skills from the session's own project root, so the dogfood project's
branch guard, gate and `python-cli-modern` skill are all inert from here — and `branch_guard` would
*silently allow* the edit, because it resolves the repo root from the session's cwd and correctly
stands down for a file outside it. Start a session in that directory instead.

What the dogfood is meant to test, none of which any test here can reach: the guard blocking the
first edit on `main`, the gate firing on save with actionable stderr, whether the skill steers, and
whether `CLAUDE.md` reads correctly mid-task rather than mid-review.

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

### 2. Decide on tagging, which changes update semantics

The template has **no git tags**, so `.copier-answers.yml` records a bare commit hash and the
`--vcs-ref v1.3.0` examples in the README refer to tags that do not exist yet.

This is not just a labelling gap. **Once any tag exists, `copier update` pulls to the latest tag
rather than `HEAD`.** That is correct for stable releases and wrong while the template is being
iterated on, because fixes stop propagating to the dogfood until they are tagged. Current decision:
stay untagged until the dogfood settles, then cut `v0.1.0` and fix the README examples to match
whatever scheme is chosen.

### 3. Verify generation into unusual git states

Still unverified:

- A destination directory that is already a git repo, and one whose default branch is not `main`
  (`branch_guard` takes `--protected main master`).
- The generation tasks assume `git init -b main` succeeds, i.e. that nothing is there yet.

### 4. Decide whether `mcp-debugger` ships

Still user-scope only, deliberately: project scope would force **Node 22+ onto every generated
Python project**. `debugpy` is already a dev dependency, so the Python half travels regardless.

## Nice to have

- **The generation-tests hook is `always_run`.** Even `prek run --files README.md` triggers the full
  minute-long suite; `--skip generation-tests` is the workaround. A `files:` pattern limiting it to
  changes under `template/`, `copier.yml` and `tests/` would be better.
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
