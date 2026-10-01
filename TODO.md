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

## In flight

### Dogfood in `GrndZero101/template-dogfood`

A private consumer repo, generated from the published template as `cli-modern`. It has since grown a
`weather` subcommand, renamed its script to `tdf-cli`, and taken two `copier update`s: to `ba78c6d`,
then to `31e9fa8` (the scaffold). Both merged and pushed, gate green, now 104 tests. Those updates
and the first agent-driven debugging session produced items 1 and 2 below.

**This cannot be driven from a session rooted in `python-template`.** Claude Code loads
`.claude/settings.json` and skills from the session's own project root, so the dogfood project's
branch guard, gate and `python-cli-modern` skill are all inert from here — and `branch_guard` would
*silently allow* the edit, because it resolves the repo root from the session's cwd and correctly
stands down for a file outside it. Start a session in that directory instead.

**The scaffold update removed code the dogfood still used**, deliberately: it deleted `geo.py`,
`currency.py` and their tests, dropped `httpx` and moved `OutputOption` (now defaulting to `None`)
into `options.py`, while the dogfood's own `weather.py` imports both. It was rehearsed on a scratch
clone first (`_src_path` edited, `copier update --trust --defaults --vcs-ref refactor/cli-minimal`),
then run for real from a session rooted in the dogfood. **The rehearsal predicted the real run
exactly** — same four conflicts, same silent `httpx` drop, same fix, same 104 tests — so a scratch
rehearsal is a trustworthy dry run. What the rehearsal found:

- The three files the dogfood never edited were **deleted**, cleanly. Untested: a removed file the
  project *had* edited — the dogfood's `currency.py` turned out identical to the template's.
- Four conflicts, all inline markers: `README.md`, `cli.py`, `typer_entrypoint.py`, and
  `tests/test_typer_entrypoint.py`. The last is a file the **dogfood added itself** that the
  template now also ships — a same-name collision, merged as a conflict rather than overwritten.
- `httpx` was dropped from `pyproject.toml` **without** a conflict, though `weather.py` imports it.
  The gate caught it — `ty` reported the unresolved import, and the moved `OutputOption` — but
  **only after `uv sync`**. Until then the venv still holds `httpx` and `ty` passes. The README's
  update section should say: `copier update`, resolve, `uv sync`, then `prek run --all-files`.
- The documented migration (`uv add httpx`, `OutputOption = None` resolved through
  `load_settings`) was sufficient, except for two log-assertion tests using the old geo pattern:
  a pre-added loguru sink is removed by the callback's `configure_logging`. Switching them to
  `capsys` stderr fixed it; the skill now says so. After that: 104 tests, gate clean.

What only the real run showed — how the conflicts read to an agent meeting them cold — is under
item 2.

What the dogfood is meant to test, none of which any test here can reach: the guard blocking the
first edit on `main`, the gate firing on save with actionable stderr, whether the skill steers, and
whether `CLAUDE.md` reads correctly mid-task rather than mid-review.

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
- Minor, upstream: `stop_debugging` always appends a "root cause analysis checkpoint" lecture, and
  the `start_debugging` description tells the agent to load a `debug-live` skill that is not
  installed when the server is registered by hand.

### 2. Hook and update robustness, found during the first `copier update`

- **A conflicted `pyproject.toml` locks every edit.** The `PreToolUse` guard runs through `uv run`,
  which parses `pyproject.toml` before anything else, so a conflict marker in it fails the guard —
  blocking the very edit that would resolve the conflict. Fails closed, which is right, but the only
  way out was a shell edit. The guard should be launchable without `uv` parsing the project.
- **Hook commands use relative paths** (`tools/branch_guard.py`). They resolve against the
  shell's current directory, so after any `cd` elsewhere every hook fails. Also fails closed, but
  the error (`can't open file`) does not say why. `$CLAUDE_PROJECT_DIR` would fix it but needs
  expanding, which runs into the one-executable rule; needs a decision. Hit again while recording
  these notes: one `cd` into `python-template` for a `git` command, and every later `Edit` from the
  dogfood session failed until the shell was moved back. `git -C <dir>` avoids it.
- **`check-merge-conflict` does not see copier's conflict markers.** It only inspects files while a
  git merge is in progress, which a copier update is not. `ruff` and `ty` caught the markers in
  Python; nothing would catch them in Markdown or YAML. Confirmed on the real `31e9fa8` update: the
  hook printed `Passed` with markers in four files.
- **The edit gate floods during conflict resolution.** `ty` checks the whole project on every save,
  so each edit to one conflicted file reprinted 60–80 syntax diagnostics from the *other* three —
  thousands of lines per edit, burying the one result that mattered. It pushed the agent from
  hunk-by-hunk edits to whole-file resolution (`git checkout --theirs`). Options: have `gate.py`
  stand down while any tracked file holds a conflict marker and say so in one line, or scope `ty`'s
  output to the edited file.
- **The gate's autofix deletes an import added ahead of its use.** Adding `load_settings` and
  `global_options` to `weather.py`'s imports in one edit, then the call site in the next, let
  `ruff check --fix` strip both imports as unused (`F401`) in between; the call site then failed as
  undefined names. Every refactor an agent does in more than one edit hits this. Either mark `F401`
  `unfixable` in the edit-time gate (still reported, never removed — `prek run` at commit can keep
  fixing it), or tell agents in `CLAUDE.md` to land the use before or with the import.
- **Conflict labels do not say which side is newer work.** copier labels the sides
  `before updating` (the project) and `after updating` (the new template render). In
  `typer_entrypoint.py` the project side was the dogfood's own missing-argument help (`27c9ad8`),
  and the template side was that same feature upstreamed with changed semantics — help to stderr,
  exit 2 instead of 0. Telling "the template superseded this" from "the project customised this"
  took reading both sides and the dogfood's history. A line in the update notes for each release
  naming features absorbed from consumers would settle it. Worth knowing for the README: index
  stage 3 is the new template render, so `git checkout --theirs <file>` takes it whole — which also
  drops project-only lines sitting *outside* the markers (here, a now-dead private `echo` import
  that a hunk-by-hunk resolution would have kept until `F401` caught it).
- **A moved option is a silent interface break for consumer commands.** `weather` had its own
  `-v/--verbose`; on the scaffold that flag is global, so `tdf-cli weather -v cleve` became
  `tdf-cli -v weather cleve`. The template's `!` commit covers its own commands, but nothing warns a
  consumer that commands *it* wrote need the same change. The update notes should say so.
- **A new question takes its default on update.** `script_name` was added after the dogfood was
  generated, and `copier update --defaults` recorded `template-dogfood`, re-proposing the rename in
  every file carrying the name. Fixed in the dogfood by recording `tdf-cli` in
  `.copier-answers.yml`. The README's update section should say to run without `--defaults`, or
  with `--data <question>=<value>`, whenever the template has added questions.
- **`copier update` needs `--trust`** because the template has `_tasks`, even though every task is
  guarded to `copy`. Worth a line in the README, since it is also the flag an agent's permission
  classifier refuses.

### 3. Run the `examples/` specs as dogfood exercises

`examples/geo.md` and `examples/currency.md` describe the removed demo commands as specs: flags,
service, output, failure modes and the tests that should exist, but no structure. Hand one to an
agent in a session rooted in a generated project and record what the template steered and what it
missed. The original code is at `d8e26b0` for comparison.

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
adapters launching through it. Worth doing after item 1, so the `python` adapter's launcher is
proven on both platforms at once.

Known CLI gaps, all worked around in the skill rather than fixed: it ignores `launch.json`; it
always sets `program`, so pytest needs the shim (and, per item 1, so does every `src/` module);
complex values render as dunder trees unless wrapped in `repr()`; the debuggee's output is not
captured, and neither is logpoint output.

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
