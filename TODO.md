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
- Toolchain: `uv`, `ruff`, `ty`, `prek`, `rumdl`, `copier` 9.17.0. Five modules under
  `template/tools/`: `check_nested_defs` (no linter covers `def` inside `def`), `branch_guard` and
  `gate` (the two hooks), `hook_payload` (shared parsing so they cannot diverge), and
  `debug_pytest` (the DebugMCP pytest shim).
- Guards live: `PreToolUse` blocks edits to *repo* files on `main`, `no-commit-to-branch` blocks
  direct commits while still permitting `--no-ff` merges, `conventional-pre-commit` checks every
  message, `SessionStart` reports branch and tree state.
- Hooks are **exec form** (`command` + `args`, no shell) with `${CLAUDE_PROJECT_DIR}` paths, so a
  `cd` cannot break them, and launch through `uv run --no-project --no-config`, so a conflicted
  `pyproject.toml` cannot either. Both hooks find the repository by walking up from the *edited
  file*, bounded by the session's project, so a nested worktree is judged by its own branch.
- `copier update` is guarded at both gates. The edit-time gate **pauses** while any file holds
  conflict markers, listing them instead of reprinting every file's syntax errors;
  `check-merge-conflict` runs with `--assume-in-merge`, so it sees copier's markers at commit; and
  `unused-import` is `unfixable`, so an import added an edit ahead of its use survives.
- `cli-modern` ships a **scaffold**, not a demo: one placeholder `about` command, a global
  `--verbose`/`--version` and a per-command `--output`, each resolving flag, then environment
  variable (`<SCRIPT>_*`), then default through `pydantic-settings`. The old `geo`/`currency`
  demo became specs under `examples/` — see item 3 for how they are meant to be used.
- A file under `template/` is `.jinja` only when it names something an answer decides; root
  `CLAUDE.md` lists them. The remaining source modules ship literally because their internal
  imports are **relative** — nothing inside `src/` names the package.
- `template/` cannot be linted in place (Jinja, no `pyproject.toml`). `tests/test_template.py` is
  the only thing that verifies it: tests that generate a project per type and run that project's
  gate and suite inside it. Wired into the gate; costs about a minute.
- Agent debugging is the **standalone DebugMCP CLI** (`debugmcp` on npm, Microsoft), which
  replaced `mcp-debugger`. Projects ship `.debugmcp.json` (a `python` and a `pytest` adapter, both
  `uv run python -m debugpy.adapter`), `tools/debug_pytest.py` and the `python-debug` skill; the
  server itself is registered per user, so no generated project needs Node. Proven headless in
  WSL against 0.1.3: breakpoints, conditional breakpoints on one parametrized case, stepping and
  evaluation, for a script and for a pytest file. "A script" there meant a standalone file: any
  module under `src/` fails under the `python` adapter (item 1).
- **Dogfood:** `GrndZero101/template-dogfood`, a private `cli-modern` consumer with its own
  `weather` command and script `tdf-cli`. It has taken three `copier update`s, to `ba78c6d`,
  `31e9fa8` and `de20fe3`; gate green, 115 tests, pushed. A fresh session there confirmed the
  exec-form hooks on a consumer: `SessionStart` reports, the guard blocks a write on `main`, and
  on a branch the gate blocks a nested def after the save. The guard also refuses when run from
  outside the repository, so `--directory ${CLAUDE_PROJECT_DIR}` holds. A rehearsal on a scratch
  clone (`_src_path` edited, `copier update --trust --defaults --vcs-ref <branch>`) predicted the
  real `31e9fa8` run exactly, so it is a trustworthy dry run. **Drive it from a session started
  in its own directory** — Claude Code loads hooks and skills from the session's project, so from
  here its guard, gate and skills are all inert. It exists to test what no test here can: the
  guard on the first edit, the gate's stderr on save, whether the skills steer, and how
  `CLAUDE.md` reads mid-task.

## Do next

### 1. Fix what the first agent debugging session found

Driven from a real Claude Code session in `template-dogfood`, following the `python-debug` skill,
against DebugMCP CLI 0.1.3 in WSL. The `pytest` adapter works: breakpoints, stepping, `repr()`
evaluation, and a conditional breakpoint selecting one parametrized case. Everything else below is
broken or misleading.

- **The `python` adapter cannot run any module under `src/`.** It launches the file as a script, so
  the first relative import fails — `ImportError: attempted relative import with no known parent
  package` — and every source module uses relative imports. Because debuggee output is not
  captured, the agent sees only "ran to completion without stopping". The skill sends agents to
  exactly these modules ("a module with an `if __name__ == "__main__":` block").

  The standard fix, `"module": "pkg.cli"` (what `python -m` does), is unreachable: the CLI always
  sets `program` (`debugmcp.js`, the adapter-config builder falls back to the requested file), and
  debugpy rejects a config naming more than one of `"program", "module", and "code"`
  (`debugpy/adapter/clients.py`). Nor can it be templated, since the CLI substitutes only
  `${workspaceFolder}`, `${file}`, `${fileDirname}` and `${fileBasenameNoExtension}`.

  So use the same shape as the pytest fix: a `tools/debug_module.py` launcher as the `python`
  adapter's `program`, taking `${file}`, mapping `src/pkg/cli.py` to `pkg.cli` via
  `Path.relative_to`, and calling `runpy.run_module(name, run_name="__main__", alter_sys=True)`.
  Prototyped outside the repo: `cli.py --help` runs and exits 0. Still to do — tests, a clear error
  for a file outside `src/`, a decision on whether a non-`src` file falls back to `run_path`, and a
  breakpoint round-trip through the CLI.
- **`start_debugging` reports a miss that is not one.** With a conditional breakpoint it returned
  "ran to completion without stopping (no breakpoint hit)" while `sessionActive` was still `true`;
  `get_debug_status` with `waitForPauseSeconds` then showed it paused on the right line and case.
  The skill tells the agent to treat that message as a wrong line or condition. It should say: if
  `sessionActive` is `true`, wait on `get_debug_status` before concluding anything.
- **Logpoints are invisible.** `add_logpoint` is accepted and its output goes nowhere the agent can
  read — no tool returns it, nothing is written to disk. The skill recommends it for watching a
  value over time; it should say pause and evaluate instead.
- **The registration name collides.** The skill registers the CLI as `debugmcp`, but that is also
  the name the VS Code extension's HTTP server takes. On a machine with both, the CLI ends up as
  something else (here `debugmcp-cli`). The skill should name one and say tool names follow it.

### 2. Per-release update notes

The README's "Keeping it in sync" section now covers the update mechanics: the sequence, `uv sync`
before checking, new questions under `--defaults`, and reading copier's conflicts. What is left
depends on item 6. A release should say two things that a conflict never will: which features were
absorbed from consumers (in `typer_entrypoint.py` the "project" side was the dogfood's own feature,
superseded upstream with changed semantics), and which interface moves a consumer's *own*
commands must follow (`-v/--verbose` went global, so `tdf-cli weather -v cleve` became
`tdf-cli -v weather cleve`, and nothing warned).

### 3. Run the `examples/` specs as dogfood exercises

`examples/geo.md` and `examples/currency.md` describe the removed demo commands as specs: flags,
service, output, failure modes and the tests that should exist, but no structure. Hand one to an
agent in a session rooted in a generated project and record what the template steered and what it
missed. The original code is at `d8e26b0` for comparison.

The dogfood is current (`de20fe3`) and its exec-form hooks are proven there. The gate's pause on
conflict markers and the conflicted-`pyproject.toml` guard were not recorded firing during that
update, so treat them as proven only by the generation tests until an update with a conflict
shows them on a consumer.

### 4. Non-`cli-modern` types generate an empty package

`fastapi`, `tui`, `data` and `cli-stdlib` receive the infrastructure — `tools/`, `CLAUDE.md`, the
gate, the hooks, their one skill — but `src/<package>/` contains only `__init__.py` and `py.typed`.
That is honest (the `geo`/`currency` demo is a typer demonstration and would drag typer, httpx and
rich into an unrelated stack) but it gives those projects nothing to pattern-match against.

Each needs a small placeholder in its own idiom, on the pattern `cli-modern` now sets — the
smallest runnable, tested thing that exercises the plumbing, not a demo to delete: an argparse
`about` for `cli-stdlib`, a FastAPI `/health` route with an `ASGITransport` test, a single-screen
Textual app with a Pilot test, a single polars/duckdb pipeline function. Each should resolve its
settings the same way (flag, env var, default), so the configuration story is uniform across types.

Note `logging_setup.py` is currently excluded from those types because it imports `loguru`. A
stdlib `logging` equivalent is probably the right shared default, with the loguru one shipping only
where a skill calls for it.

### 5. A config-file layer for settings

Today settings resolve flag, then environment variable, then default. The missing layer is a
**user config file** between the environment and the defaults. Proposed shape:

- **Location by platform convention.** `$XDG_CONFIG_HOME/<script>/config.toml` (falling back to
  `~/.config`) on Linux and other Unix-alikes; `%APPDATA%\<script>\config.toml` on Windows — the
  roaming profile, since settings should follow the user, unlike caches, which belong in
  `%LOCALAPPDATA%`. `platformdirs.user_config_dir(appname, appauthor=False)` gives exactly this
  mapping; without `appauthor=False` it inserts an extra author directory on Windows.
- **Open question: macOS.** `platformdirs` says `~/Library/Application Support/<app>`, but most
  CLI users expect `~/.config` there too. Probably honour `XDG_CONFIG_HOME` when set on any
  platform, and decide the macOS default deliberately.
- **Override the location** with a global `--config PATH` and `<SCRIPT>_CONFIG`, so tests and CI
  never read a real user file.
- **TOML**, read through pydantic-settings' own TOML source via `settings_customise_sources`
  (check the current docs for the class name and signature), so one validation pass still covers
  every layer and error messages can name the file.
- **Tests** point the location at `tmp_path`; nothing may read the developer's real config.
- Decide whether a project-local file (`./<script>.toml`) is also wanted. It is a second source
  of surprise; leave it out unless a real need appears.

### 6. Decide on tagging, which changes update semantics

The template has **no git tags**, so `.copier-answers.yml` records a bare commit hash and the
`--vcs-ref v1.3.0` examples in the README refer to tags that do not exist yet.

This is not just a labelling gap. **Once any tag exists, `copier update` pulls to the latest tag
rather than `HEAD`.** That is correct for stable releases and wrong while the template is being
iterated on, because fixes stop propagating to the dogfood until they are tagged. Current decision:
stay untagged until the dogfood settles, then cut `v0.1.0` and fix the README examples to match
whatever scheme is chosen.

### 7. Verify generation into unusual git states

Still unverified:

- A destination directory that is already a git repo, and one whose default branch is not `main`
  (`branch_guard` takes `--protected main master`).
- The generation tasks assume `git init -b main` succeeds, i.e. that nothing is there yet.

### 8. Prove the DebugMCP CLI on Windows native, later

The agent-session half is done (item 1) — in WSL. Still unverified, and needing a session started
on Windows itself: the `cmd /c` registration, `uv` resolving as the adapter command, and both
adapters launching through it. The same session should confirm the exec-form hooks: exec form on
Windows needs `command` to be a real `.exe`, which `uv` and `git` are, but nothing has run them
there yet. Worth doing after item 1, so the `python` adapter's launcher is
proven on both platforms at once.

Known CLI gaps, all worked around in the skill rather than fixed: it ignores `launch.json`; it
always sets `program`, so pytest needs the shim (and, per item 1, so does every `src/` module);
complex values render as dunder trees unless wrapped in `repr()`; the debuggee's output is not
captured, and neither is logpoint output. Upstream and minor: `stop_debugging` always appends a
"root cause analysis checkpoint" lecture, and the `start_debugging` description tells the agent to
load a `debug-live` skill that is not installed when the server is registered by hand.

### 9. The DebugMCP VS Code extension, later

Deferred by choice. It drives VS Code's own debugger over HTTP on `localhost:3001` and reuses
`launch.json`, but it uses the interpreter selected for the *open window*: from a
`python-template` window it launched the system Python and failed to import the package. Open
questions: two windows contending for one port, and coexisting with the CLI, since
`debugmcp configure` keeps a single `debugmcp` entry and replaces whichever is there.

## Nice to have

- **Gate instrumentation.** Append pass/fail from the `PostToolUse` hook to a gitignored
  `.gate.log` for a hard count of how often the gate catches something.
- **The generation tests are not offline.** `uv sync` runs during generation and reaches the
  network on a cold cache. Everything else about them is deterministic.
