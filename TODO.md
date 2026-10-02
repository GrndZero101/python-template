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
- Toolchain: `uv`, `ruff`, `ty`, `prek`, `rumdl`, `copier` 9.17.0. Six modules under
  `template/tools/`: `check_nested_defs` (no linter covers `def` inside `def`), `branch_guard` and
  `gate` (the two hooks), `hook_payload` (shared parsing so they cannot diverge), and
  `debug_module` and `debug_pytest` (the DebugMCP launchers for a source file and a test file).
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
  demo became specs under `examples/` — see phase 2 for how they are meant to be used.
- A file under `template/` is `.jinja` only when it names something an answer decides; root
  `CLAUDE.md` lists them. The remaining source modules ship literally because their internal
  imports are **relative** — nothing inside `src/` names the package.
- `template/` cannot be linted in place (Jinja, no `pyproject.toml`). `tests/test_template.py` is
  the only thing that verifies it: tests that generate a project per type and run that project's
  gate and suite inside it. Wired into the gate; costs about a minute.
- Agent debugging is the **standalone DebugMCP CLI** (`debugmcp` on npm, Microsoft), which
  replaced `mcp-debugger`. Projects ship `.debugmcp.json` (a `python` and a `pytest` adapter, both
  `uv run python -m debugpy.adapter`), `tools/debug_pytest.py` and the `python-debug` skill; the
  server itself is registered per user (as `debugmcp-cli`, since the VS Code extension takes
  `debugmcp`), so no generated project needs Node. Proven headless in WSL against 0.1.3:
  breakpoints, conditional breakpoints on one parametrized case, stepping and evaluation, for a
  pytest file, a `src/` module with relative imports (`cli.py`, via `tools/debug_module.py`, which
  runs it as `python -m` would) and an ad-hoc script outside `src/` (which falls back to running by
  path). Neither adapter can pass the program arguments, so the skill sends commands through
  their tests.
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

## The plan

Built from a review on 2026-10-02 against three goals: well-structured DevOps and QOL CLI tools;
code a person can maintain and step through; and token efficiency, meaning a lower-reasoning model
can build a good tool because the skills, tooling and hooks carry the knowledge. Every defect below
was reproduced in a project generated from `main` at `712a7f8`, not inferred from reading.

**CLI comes first.** Phases 1–8 make `cli-modern` and `cli-stdlib` right. Phases 9–12 then build
out `data`, `tui` and `fastapi` on the same pattern. Items within a phase are independent unless
noted, and each can be its own branch.

**Done means**, for every item: the generation suite (`uv run pytest`) and `prek run --all-files`
pass, and anything that changes what a skill tells a model has been run through a generated
project's gate, not just read. A phase that changes what generated projects receive ends with a
`copier update` of the dogfood, run by hand as the README describes.

### Decisions needed

| # | Decision | Needed by | Recommendation |
|---|---|---|---|
| D1 | Python floor: render `.python-version` from the answer, or keep 3.14 and test the floor in CI only | Phase 1 | **Decided:** render it from the answer, keeping 3.14 as the question's default. The gate and the tests then prove the floor on every run. |
| D2 | Benchmark spend: which models, how many runs per spec | Phase 2 | Haiku and Sonnet, three runs each, on both existing specs. |
| D3 | Git ritual: prose in a skill, or a script the skill calls | Phase 6 | A script. A multi-step ritual in prose is where weaker models slip. |
| D4 | `cli-stdlib`: finish it with an argparse scaffold, or replace it with a PEP 723 single-file `scripts` type | Phase 7 | Finish it; reconsider once the benchmark has numbers. |
| D5 | Tagging, which changes `copier update` semantics | Phase 8 | Unchanged: tag `v0.1.0` once the dogfood settles. |
| D6 | Shape of `data` and `tui`: build on the `cli-modern` CLI layer, or each in its own idiom | Phase 9 | Build on the CLI layer. Both are CLI tools that happen to crunch data or draw a screen. |
| D7 | Order of the secondary types | Phase 9 | `data`, then `tui`, then `fastapi`: nearest to the CLI first. |

### Phase 1 — Fix what is broken (CLI and shared)

All nine defects are fixed on `fix/phase1-defects`, 2026-10-02: `--trust` on every copier command;
the `python-cli-modern` examples run through a generated gate; `python-cli` stack-agnostic, with no
`publicip` and no contradictions with the scaffold; prek forms only for the lint commands; ruff's
fixer before its formatter; F5 through `tools/debug_module.py`; `python_version` a choice of
3.12–3.14 rendered into `.python-version`, with every type proven at 3.12; and the `T20` and
`from None` table rows corrected.

- [ ] **`copier update` the dogfood** to the phase 3 merge commit (it covers phase 1 too), by hand
  as the README describes. Phase 1's part touches `.python-version` (now rendered), the prek config
  (hook order), `launch.json`, CLAUDE.md and three skills; phase 3 adds four `tools/` modules and
  their tests, and new `Stop` and `SessionStart` hooks in `.claude/settings.json`. Expect conflicts
  only where the dogfood edited those files. Its `weather.py` has three `raise ... from None`, which
  CLAUDE.md now names as a violation: line 69 drops a `JSONDecodeError`, and lines 134 and 137 raise
  `typer.Exit`. All three become `from exc`. For an exit signal that changes nothing at runtime,
  which is why phase 5's check needs no exemption for it. Fix them in the dogfood, from a session
  started there.

### Phase 2 — A benchmark harness and a baseline

Moved ahead of the improvements so each later phase is measured against a baseline rather than
judged by feel. Nothing has yet run this template with a lower-reasoning model, which is the claim
goal three makes.

- [ ] **A harness under `bench/`**, not shipped. For one spec and one model: generate a fresh
  `cli-modern` project, cut a branch so the guard does not stop the first edit, run
  `claude -p "<spec>" --model <model> --output-format json` with the project as its working
  directory so its hooks and skills load, then run the project's own `prek run --all-files` and
  `uv run pytest`. Record `total_cost_usd`, turns, duration, gate blocks (from `.gate.log`) and
  pass or fail. Flags checked against Claude Code 2.1.287: `-p "$(cat spec.md)"`, `--model`,
  `--output-format json` (or `stream-json` for every tool call), `--permission-mode acceptEdits`,
  `--allowedTools` (the project allowlist covers `uv run` and `prek`, not `git`),
  `--max-budget-usd`, `--no-session-persistence` and `--strict-mcp-config`. Never `--bare`: it
  skips the hooks being measured. Open: whether `--setting-sources project,local` also keeps the
  user's own `~/.claude` rules out of the run, so the baseline measures the template alone.
- [ ] **Score against the spec, not only the gate.** Each spec in `examples/` lists the tests that
  should exist and a failure table. A short checklist per spec turns that into a score.
- [ ] **A baseline straight after phase 1**, per D2, so broken documentation does not dominate the
  numbers. Re-run after phases 3, 5 and 6, and record every run's numbers here.
- [ ] Carried over: the original demo code is at `d8e26b0` for comparison. The gate's pause on
  conflict markers and the conflicted-`pyproject.toml` guard are still proven only by the
  generation tests, not by a consumer update with a real conflict.

### Phase 3 — Make the gate precise and unavoidable

Done on `feat/phase3-gate`, 2026-10-02. The edit-time gate reports failures only, concisely —
`prek --quiet` plus `RUFF_OUTPUT_FORMAT` and `TY_OUTPUT_FORMAT` set to `concise` (ty honours the
variable through `uv check`), 266 bytes where it was 3,048 — and re-runs once when prek only
applied its own fixes. With prek missing it says so to the agent and the user. A `Stop` hook,
`tools/stop_gate.py`, gates every changed and untracked file and runs the tests, blocking once
per stop. `tools/session_doctor.py` reports a missing `prek` or git shim at session start.
Notebook edits are guarded and gated. Every gate and stop-gate run appends a line to `.gate.log`.

Left for the dogfood update below: a fresh session there should show the doctor's status line, a
`sed` edit caught by the stop gate, and a `.gate.log` filling up.

### Phase 4 — Stabilise the toolchain

- [ ] **Stop preview rules arriving by prefix.** With `preview = true`, prefix selection enables 120
  preview rules on ruff 0.16.0, any of which can change, or be joined by new ones, in a ruff bump.
  One already rewrote a `# noqa: E731` into `# ruff: ignore[lambda-assignment]` during the gate.
  Set `explicit-preview-rules = true` and select the wanted ones by code: `PLR1702`, `PLR0914` and
  `PLW1514`. That also drops `no-self-use` (`PLR6301`), which fires on every Textual `compose()`.
- [ ] **Bump the hook pins** and fix whatever the new versions report: ruff v0.16.0 to v0.16.10,
  ty v0.0.64 to v0.0.84, rumdl v0.2.45 to v0.2.78, uv-pre-commit 0.12.0 to 0.12.22. Automating
  this belongs to phase 8.
- [ ] **pytest strictness.** pytest 9 has `strict = true` (strict config, markers, xfail and
  parametrization ids). With `filterwarnings = ["error"]`, a typer or pydantic deprecation fails a
  test the day it appears rather than at the next major version.

### Phase 5 — Turn conventions into checks

Every rule a weak model has to remember is one it will eventually skip. Five rows of CLAUDE.md's
"convention — review only" list are cheap AST checks, and a probe through the gate confirmed none of
them is flagged today.

- [ ] **Grow `check_nested_defs.py` into a conventions checker**, with a rule id per check, the same
  per-line opt-out, and a message that names the fix: a `class` inside a function; a comprehension
  with more than one `for`, or a nested comprehension; `raise ... from None`; `getattr` with a
  non-literal attribute name; and a module that defines `main` without an
  `if __name__ == "__main__":` block. Move the table rows from "convention" to the checker. A rename
  touches the hook id, both configs, CLAUDE.md, the READMEs and the tests.
- [ ] **Make "add a setting" fail loudly when a step is missed.** It is four coordinated edits
  today: `Settings`, `_Overrides`, `load_settings` and an option alias in `options.py`. Add a test
  that the field names of the first three agree and that every field's environment variable
  appears in some option's help. Consider a shape with fewer places to touch.

### Phase 6 — Cut the always-loaded context; make the skills recipes

CLAUDE.md is paid for in every session, and a skill every time its task comes up — in tokens, and
past a point in adherence. Anthropic's guidance is under 200 lines per CLAUDE.md, with task-specific
workflows in skills; imports do not reduce the cost.

- [ ] **Move the git ritual out of CLAUDE.md.** `template/CLAUDE.md` is 283 lines, and lines 118-263
  — branching, merging, commits — are about half of it. Keep a ten-line summary (never edit on
  `main`, branch names, Conventional Commits, one change per commit, how to finish a branch) and
  move the rest into a `git-workflow` skill. Per D3, encode the squash-and-merge procedure in a
  script the skill calls, so the steps are run rather than remembered. This repo's CLAUDE.md
  imports the template's, so sessions here load 377 lines; it shrinks with it.
- [ ] **A recipe-first `python-cli-modern`.** It is 441 lines, mostly rationale, with no step list.
  Open with two checklists — add a command, add a setting — naming each file to touch and each
  test to write. Move httpx, concurrency, prompts, completion and the pydantic and SQLModel notes
  into reference files beside `SKILL.md`, linked from where they apply.
- [ ] **Copyable reference files.** A command module with its test, shaped like `about.py`; and an
  httpx client factory with per-phase timeouts, a descriptive User-Agent, retry on 429 and 5xx
  honouring `Retry-After`, and debug logging of each request. A weak model copying a vetted file
  beats one synthesising it from prose.
- [ ] **Skill code is checked code.** Every phase 1 skill defect was an example nobody had run.
  Either keep examples in reference `.py` files that a generation test lints inside a project that
  has their dependencies, or have a generation test pull the complete code blocks out of every
  shipped skill and run them through the gate. Pick one, and apply it to the secondary skills too.
- [ ] **Move the infrastructure tests out of `tests/`.** In a fresh project, 1,539 of 2,313 Python
  lines are template machinery, and six of the ten test files test hooks. Move them to
  `tools/tests/` so `tests/` holds only the product a model pattern-matches against. `testpaths`,
  `pythonpath` and `BASE_TESTS` in `tests/test_template.py` follow.
- [ ] **One home for each rationale.** The scaffold's docstrings, the skill and CLAUDE.md repeat the
  same reasoning (why options default to `None`, why not `envvar=`, why the script is not `cli`,
  shell completion). The copies have drifted once already. Keep the reasoning in the skill and a
  one-line pointer in the docstring.

### Phase 7 — DevOps CLI features

- [ ] **Secrets.** Following `config.py`'s own recipe with `api_token: str` leaks the token twice:
  in `about -o json` on stdout and in the `-v` debug log on stderr. Nothing in CLAUDE.md, the skills
  or the scaffold mentions `SecretStr`. Teach it in the "add a setting" recipe, reading the value
  with `.get_secret_value()` only where the client is built, and add a test that a secret setting
  renders masked in `about`'s table, its JSON and the debug log.
- [ ] **A config-file layer.** Today settings resolve flag, then environment variable, then
  default. The missing layer is a **user config file** between the environment and the
  defaults. Proposed shape:
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
- [ ] **A `cli-stdlib` scaffold** (per D4): an argparse `about` resolving flag,
  then environment variable, then default like `cli-modern`, with its tests, and a stdlib `logging`
  setup to go with it, since `logging_setup.py` is loguru and travels only with `cli-modern`.
- [ ] **An install story in the generated README**: how a user puts the tool on their PATH
  (`uv tool install .`, or from git) and how a version is bumped. Ties to phase 8.

### Phase 8 — CI, releases and updates

- [ ] **CI for this repo.** A GitHub Actions workflow running the generation suite on Ubuntu,
  Windows and macOS. It would check on every push the portability rules that only convention and
  WSL cover today, and the generation tests that spawn hooks exactly as Claude Code would go a long
  way toward the hooks half of "DebugMCP on Windows native" under Later.
- [ ] **CI shipped in generated projects**: the same matrix running `prek run --all-files` and
  `uv run pytest`, so a generated tool is checked away from its author's machine too.
- [ ] **Pin automation.** Nothing bumps the hook pins or the dependency floors, and they drifted
  10–20 releases in two months. A scheduled `prek update` workflow, or Renovate, gated by the
  generation suite.
- [ ] **Tagging** (D5). The template has **no git tags**, so `.copier-answers.yml`
  records a bare commit hash and the `--vcs-ref v1.3.0` examples in the README refer to tags that
  do not exist yet. This is not just a labelling gap. **Once any tag exists, `copier update` pulls
  to the latest tag rather than `HEAD`.** That is correct for stable releases and wrong while the
  template is being iterated on, because fixes stop propagating to the dogfood until they are
  tagged. Current decision: stay untagged until the dogfood settles, then cut `v0.1.0` and fix the
  README examples to match whatever scheme is chosen.
- [ ] **Per-release update notes.** The README's "Keeping it in sync" section now covers the
  update mechanics: the sequence, `uv sync` before checking, new questions under `--defaults`,
  and reading copier's conflicts. What is left depends on tagging. A release should say two things
  that a conflict never will: which features were absorbed from consumers (in
  `typer_entrypoint.py` the "project" side was the dogfood's own feature, superseded upstream with
  changed semantics), and which interface moves a consumer's *own* commands must follow
  (`-v/--verbose` went global, so `tdf-cli weather -v cleve` became `tdf-cli -v weather cleve`, and
  nothing warned).
- [ ] **Generation into unusual git states**, a natural CI job. Still unverified: a
  destination directory that is already a git repo, and one whose default branch is not `main`
  (`branch_guard` takes `--protected main master`); and the generation tasks assume
  `git init -b main` succeeds, i.e. that nothing is there yet.

### Phase 9 — Groundwork for the secondary types

`fastapi`, `tui` and `data` receive the infrastructure — `tools/`, CLAUDE.md, the gate, the hooks,
one skill — and an empty package. Their skills were written but never run against a generated
project, and probes in the review found each broken somewhere a first attempt would hit.

- [ ] **Settle D6 and D7.** The recommendation: `data` and `tui` build on the `cli-modern` CLI layer
  (typer entry point, settings, logging, `about`) and each add one command of their own, since both
  are CLI tools; Textual already depends on rich. `fastapi` shares the configuration and logging
  conventions without typer: settings from the environment only, through pydantic-settings.
- [ ] **Logging.** `logging_setup.py` is excluded from the other types because
  it imports `loguru`. A stdlib `logging` equivalent is probably the right shared default, with the
  loguru one shipping only where a skill calls for it. FastAPI adds uvicorn's own loggers to the
  question.
- [ ] **Restructure `_exclude` around layers** rather than repeating every `cli-modern` file per
  type, and keep the sets in `tests/test_template.py` in step.
- [ ] **One definition of done for every type**: a scaffold that is the smallest runnable, tested
  thing exercising its plumbing (not a demo to delete); a recipe-first skill with reference files;
  its code checked by the phase 6 mechanism; a generation test; a spec under `examples/`; and a
  benchmark run.

### Phase 10 — `data`

Verified defects in today's skill:

- [ ] `con.sql(...).fetchone()[0]` (`python-data/SKILL.md`, lines 95 and 109) fails ty, because
  `fetchone()` returns `tuple | None`. Show the `None` check, or fetch through `.pl()`.
- [ ] `LazyFrame.profile()` is recommended as a debugging tool but has been deprecated since polars
  1.43 — the version the skill says it was verified against. polars' docs say the streaming engine
  becomes the default in 2.0, which makes per-node profiling misleading. Replace it, and re-verify
  the skill against polars 1.44 and duckdb 1.5.

Build-out:

- [ ] **Scaffold:** a `summarize INPUT` command over a pure pipeline function that scans with an
  explicit schema, names each intermediate frame and collects once; `--output table|json`, plus
  parquet to a file. Settings resolve flag, then environment variable, then default, as in the CLI.
- [ ] **Tests:** five-row frames built inline, fixture parquet written to `tmp_path`, the schema
  asserted alongside the values, `assert_frame_equal`, and a sort after every `group_by`.
- [ ] **Skill additions:** an "add a pipeline stage" recipe; `rel.pl(lazy=True)` to hand a duckdb
  result to polars lazily; parameterised duckdb queries rather than f-strings.
- [ ] **Spec:** one under `examples/` to benchmark — a log or billing-export summariser, say.

### Phase 11 — `tui`

Verified defects in today's setup and skill:

- [ ] The first Pilot test fails with "async def functions are not natively supported": no async
  test plugin ships. Add `pytest-asyncio` to the tui dev group with `asyncio_mode = "auto"`, as
  Textual's testing guide does.
- [ ] `textual console` and `textual run --dev`, which the skill's debugging section depends on,
  come from `textual-dev`, which is not installed. Add it to the tui dev group.
- [ ] Idiomatic Textual fails the gate three ways: `BINDINGS = [...]` trips `mutable-class-default`
  (annotate it `ClassVar[list[BindingType]]`); `compose()` trips `no-self-use` (gone after phase 4,
  or add `@override`); and a handler that ignores its event trips `unused-method-argument` (Textual
  lets a handler omit the event parameter — teach that).
- [ ] The floor is `textual>=7.2.0`, but 8.2.8 is current, a major version on. Re-verify the skill
  against 8.x.

Build-out:

- [ ] **Scaffold:** a single-screen app launched by a `tui` command, its logic in a `domain.py` with
  no Textual import, styles in a `.tcss` file, and a Pilot test at a pinned size.
- [ ] **Debugging recipe:** stepping through the running app with debugpy (a launch line plus the
  existing attach configuration), and through the DebugMCP `pytest` adapter for logic a Pilot test
  reaches.
- [ ] **Spec:** one under `examples/` to benchmark — a log or process viewer, say.

### Phase 12 — `fastapi`

Verified defects in today's setup and skill:

- [ ] `httpx` is not installed, yet every testing route the skill offers needs it — `ASGITransport`
  directly, and `TestClient` underneath — so the first test fails at import. Add it to the fastapi
  dev group.
- [ ] The skill pairs lifespan-managed resources on `app.state` with `ASGITransport` tests, but
  `ASGITransport` does not run the lifespan: following both gives
  `AttributeError: 'State' object has no attribute ...`. Default to `with TestClient(app) as
  client:`, which runs it and needs no async plugin; for async tests, `asgi-lifespan`'s
  `LifespanManager` with `@pytest.mark.anyio`, as FastAPI's own docs do.
- [ ] A lifespan written as `yield` followed by cleanup trips `fallible-context-manager`, rightly:
  the cleanup does not run on an exception. Show `try`/`finally`, or `async with`.
- [ ] The skill says to add `"FAST"` to the lint selection; the template already does. Drop it.

Build-out:

- [ ] **Scaffold:** `main.py` (the app, its lifespan, router registration), `dependencies.py` (a
  cached `get_settings` and the `Annotated` aliases) and a `/health` router, tested through
  `TestClient`; settings from the environment through pydantic-settings, overridden in tests with
  `dependency_overrides`.
- [ ] **Skill additions:** settings as a dependency; logging alongside uvicorn's loggers; running
  with `fastapi dev` or uvicorn, and debugging the app through its tests; `SecretStr` for
  credentials; exception handlers that keep the traceback.
- [ ] **Spec:** one under `examples/` to benchmark — a small webhook receiver, say.

## Later

- **DebugMCP on Windows native.** The agent-session half is done — in WSL.
  Still unverified, and needing a session started on Windows itself: the `cmd /c` registration,
  `uv` resolving as the adapter command, and both adapters launching through it, including the
  `python` adapter's launcher, which so far is proven only on Linux. Phase 8's CI covers whether
  the exec-form hooks' `uv` and `git` resolve there; this still needs a real session. Known CLI
  gaps, all worked around in the skill rather than fixed: it ignores `launch.json`; it always sets
  `program`, so pytest and every `src/` module need a launcher, and it cannot pass the program
  arguments; complex values render as dunder trees unless wrapped in `repr()`; the debuggee's output
  is not captured, and neither is logpoint output. Upstream and minor: `stop_debugging` always
  appends a "root cause analysis checkpoint" lecture, and the `start_debugging` description tells
  the agent to load a `debug-live` skill that is not installed when the server is registered by
  hand.
- **The DebugMCP VS Code extension.** Deferred by choice. It drives VS Code's own
  debugger over HTTP on `localhost:3001` and reuses `launch.json`, but it uses the interpreter
  selected for the *open window*: from a `python-template` window it launched the system Python and
  failed to import the package. Open questions: two windows contending for one port, and coexisting
  with the CLI, since `debugmcp configure` keeps a single `debugmcp` entry and replaces whichever is
  there.
- **The generation tests are not offline.** `uv sync` runs during generation and reaches the
  network on a cold cache. Everything else about them is deterministic.
