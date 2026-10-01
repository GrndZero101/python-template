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
`weather` subcommand, renamed its script to `tdf-cli`, and taken its first `copier update` (to
`ba78c6d`): gate green, 109 tests passing, merged and pushed. That update and the first agent-driven
debugging session produced items 1 and 2 below.

**This cannot be driven from a session rooted in `python-template`.** Claude Code loads
`.claude/settings.json` and skills from the session's own project root, so the dogfood project's
branch guard, gate and `python-cli-modern` skill are all inert from here — and `branch_guard` would
*silently allow* the edit, because it resolves the repo root from the session's cwd and correctly
stands down for a file outside it. Start a session in that directory instead.

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
  expanding, which runs into the one-executable rule; needs a decision.
- **`check-merge-conflict` does not see copier's conflict markers.** It only inspects files while a
  git merge is in progress, which a copier update is not. `ruff` and `ty` caught the markers in
  Python; nothing would catch them in Markdown or YAML.
- **A new question takes its default on update.** `script_name` was added after the dogfood was
  generated, and `copier update --defaults` recorded `template-dogfood`, re-proposing the rename in
  every file carrying the name. Fixed in the dogfood by recording `tdf-cli` in
  `.copier-answers.yml`. The README's update section should say to run without `--defaults`, or
  with `--data <question>=<value>`, whenever the template has added questions.
- **`copier update` needs `--trust`** because the template has `_tasks`, even though every task is
  guarded to `copy`. Worth a line in the README, since it is also the flag an agent's permission
  classifier refuses.

### 3. Non-`cli-modern` types generate an empty package

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

### 4. Decide on tagging, which changes update semantics

The template has **no git tags**, so `.copier-answers.yml` records a bare commit hash and the
`--vcs-ref v1.3.0` examples in the README refer to tags that do not exist yet.

This is not just a labelling gap. **Once any tag exists, `copier update` pulls to the latest tag
rather than `HEAD`.** That is correct for stable releases and wrong while the template is being
iterated on, because fixes stop propagating to the dogfood until they are tagged. Current decision:
stay untagged until the dogfood settles, then cut `v0.1.0` and fix the README examples to match
whatever scheme is chosen.

### 5. Verify generation into unusual git states

Still unverified:

- A destination directory that is already a git repo, and one whose default branch is not `main`
  (`branch_guard` takes `--protected main master`).
- The generation tasks assume `git init -b main` succeeds, i.e. that nothing is there yet.

### 6. Prove the DebugMCP CLI on Windows native, later

The agent-session half is done (item 1) — in WSL. Still unverified, and needing a session started
on Windows itself: the `cmd /c` registration, `uv` resolving as the adapter command, and both
adapters launching through it. Worth doing after item 1, so the `python` adapter's launcher is
proven on both platforms at once.

Known CLI gaps, all worked around in the skill rather than fixed: it ignores `launch.json`; it
always sets `program`, so pytest needs the shim (and, per item 1, so does every `src/` module);
complex values render as dunder trees unless wrapped in `repr()`; the debuggee's output is not
captured, and neither is logpoint output.

### 7. The DebugMCP VS Code extension, later

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
