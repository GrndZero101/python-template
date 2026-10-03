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
- Toolchain: `uv`, `ruff`, `ty`, `prek`, `rumdl`, `copier` 9.17.0. Eleven modules under
  `template/tools/`: `check_conventions` and `convention_rules` (the CLAUDE.md rules no linter
  covers), the four hooks `branch_guard`, `gate`, `stop_gate` and `session_doctor`, `gate_log`,
  `hook_payload` (shared parsing so the hooks cannot diverge), and `debug_module` and
  `debug_pytest` (the DebugMCP launchers for a source file and a test file).
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
  `weather` command and script `tdf-cli`. It has taken four `copier update`s, to `ba78c6d`,
  `31e9fa8`, `de20fe3` and `b22dacd`; gate green, 193 tests, pushed. A fresh session there
  confirmed the exec-form hooks on a consumer: `SessionStart` reports, the guard blocks a write
  on `main`, and on a branch the gate blocks a nested def after the save. The guard also refuses
  when run from outside the repository, so `--directory ${CLAUDE_PROJECT_DIR}` holds. A rehearsal
  on a scratch clone (`_src_path` edited, `copier update --trust --defaults --vcs-ref <branch>`)
  predicted the real `31e9fa8` run exactly, so it is a trustworthy dry run. **Drive it from a
  session started in its own directory** — Claude Code loads hooks and skills from the session's
  project, so from here its guard, gate and skills are all inert. It exists to test what no test
  here can: the guard on the first edit, the gate's stderr on save, whether the skills steer, and
  how `CLAUDE.md` reads mid-task.

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
| D2 | Benchmark: which models, how many runs per spec | Phase 2 | **Decided, revised 2026-10-03:** by hand, no harness. Sonnet is the baseline: one run per spec, reviewed by Opus. Haiku runs now and then as a stretch measure; a haiku-only finding is recorded, not acted on, unless its fix is a cheap mechanical check that helps any model. |
| D3 | Git ritual: prose in a skill, or a script the skill calls | Phase 6 | A script. A multi-step ritual in prose is where weaker models slip. |
| D4 | `cli-stdlib`: finish it with an argparse scaffold, or replace it with a PEP 723 single-file `scripts` type | Phase 7 | Finish it; reconsider once the spec runs have findings. |
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

The dogfood took phases 1–6 in one `copier update`, to `b22dacd`, on 2026-10-03. Its one conflict
was `README.md`'s `tools/` list, which the dogfood had extended with `weather`. Its three
`raise ... from None` in `weather.py` became `from exc` in the same commit, since the update's own
`raise-from-none` check rejects them. Gate green, 193 tests, merged with `finish_branch.py`, pushed.

### Phase 2 — Spec runs and a baseline

Moved ahead of the improvements so each later phase is measured against a baseline rather than
judged by feel.

**Sonnet is the baseline (D2, revised 2026-10-03).** Sonnet met every row of the geo spec on the
template as it stood, in 9 calls. Two haiku runs took 68 calls each; the second, after the fixes
below, came close, but what it still missed was judgement — a test aimed at the wrong function,
a response parsed by hand — not knowledge the template lacked. Chasing that adds rules and prose
without end, against goal three itself. Haiku stays as an occasional stretch run.

**Decided 2026-10-03: no bespoke harness.** Each run is done by hand, as
[examples/README.md](examples/README.md) describes: a fresh project, the spec handed unedited to
the model in an interactive session, the gate and tests run by hand, then a review in a separate
`opus` session in plan mode, driven by [examples/evaluate.md](examples/evaluate.md). What a run
teaches is in the review's template findings, not in a score.

- [x] **A baseline**: both specs with `sonnet` — geo at `354b24f`, currency at `2b06886`.
- [ ] **Again after any phase** that changes what a skill or the gate tells a model.
- [ ] **Each template finding becomes an item** in the phase it belongs to.

| Date | Spec | Model | Template | Gate | Tests | `/cost` | Verdict and main findings |
|---|---|---|---|---|---|---|---|
| 2026-10-03 | geo | haiku | `354b24f` | pass | 215 pass | 68 calls, 26k out | Works live, but two required tests are wrong or missing (status error, multi-word join). Never loaded `python-cli-modern`: hand-rolled `httpx.Client()`, patched `httpx.Client.get` in every test, no response model, cause dropped on exit. |
| 2026-10-03 | geo | sonnet | `354b24f` | pass | 212 pass | 9 calls, 10k out | Meets every row. Loaded the skill second, copied `http_client.py` verbatim, `MockTransport` throughout. Wrote every file through one Bash heredoc, so the edit-time gate never ran, and committed before stopping, so the stop gate saw a clean tree. |
| 2026-10-03 | geo | haiku | `f6c03ff` | pass | pass | 68 calls, 31k out | Close. Grepped for `build_client` (named in the new `CLAUDE.md` row) and copied the reference client; `MockTransport` throughout; a real 404 for the status test. Still never loaded the skill: parsed the response by hand, tested the join on an already-joined string, and reported `exc.request.url` instead of the cause, which slipped past `silent-exit`. |
| 2026-10-03 | currency | sonnet | `2b06886` | pass | 276 pass | 15 requests, 17.7k out, $0.65 | Meets the spec; every value a `Decimal`, `parse_float=Decimal` on the response. Branched unprompted, loaded the skill second, copied the client, `Annotated` throughout. But only 3 of its 11 file writes went through the edit-time gate — the rest were heredocs and `sed -i` — and the stop gate checked nothing, because it finished onto `main` in the same turn. `finish_branch.py` failed twice on an uncommitted tree. Prompted for `git switch` and `python3`. |

The two runs together: the skill's content works and its discovery does not. A pointer in a
docstring reaches sonnet and not haiku. Fixed on `fix/spec-run-geo-findings`:

- [x] Convention rules that route a model to the skill from the code it writes: `raw-httpx-client`
  (a client built outside `build_client`), `patched-httpx` (patching httpx in a test) and
  `silent-exit` (an exit from an `except` that drops the exception). Each message names the
  reference file to copy. A repeated message is now printed once, then only its location: haiku's
  test file alone would have cost 7 KB per block.
- [x] The stop gate measured "changed" from `HEAD`, so a commit made before stopping escaped it,
  tests included. It now measures from the merge-base with `main`.
- [x] `logging_setup.py` credited every stdlib record to `logging` (an outdated frame-walking
  recipe), and `-v` printed httpcore's twenty-line wire trace per request. Loguru's current recipe,
  and httpcore held at INFO.
- [x] `build_client` passes its own transport, which makes httpx ignore `HTTPS_PROXY` and
  `NO_PROXY`: behind a proxy, every generated tool connected direct. `EnvironmentProxyTransport`
  routes by the environment.

Fixed after the second haiku run, on `fix/sonnet-baseline`, because they are wrong for any model:

- [x] `silent-exit` counted any use of the exception as reporting it, so `exc.request.url` passed
  while the reason was dropped. Only the whole exception now counts.
- [x] `nested-def` ended by suggesting the closure be returned, and haiku turned its test handlers
  into closure factories. It now leads with `functools.partial`.
- [x] Advice that repeats is printed once even when names differ: the names moved into a
  per-finding detail. Fourteen `nested-def` hits had cost about 5 KB in one block.
- [x] `examples/README.md` defaults to sonnet, unsets `VIRTUAL_ENV`, and skips
  `no-commit-to-branch` when checking a run on `main`.

Still open from these runs:

- [x] `B008` on `= typer.Argument(...)` told the model to use a module-level singleton, the wrong
  fix for typer, and missed `str` and `int` annotations entirely. Fixed on
  `fix/typer-default-and-backoff`: a `typer-default` convention rule names `Annotated` for any
  annotation, and `typer.Argument` and `typer.Option` are in bugbear's `extend-immutable-calls`,
  so `B008` stays silent on them and on for everything else. The scaffold still has no positional
  argument; the rule's message and the "add a command" recipe now show one, and `status.py` has
  one to copy. Proven in a generated project: a `list[str]` argument and an `int` option in the
  old form give two `typer-default` hits and no `B008`.
- [x] `build_client` retried a 5xx after 0.5 s, which breaks an API's one-request-per-second
  policy, Nominatim's for one. `backoff=` now sets the first wait, through `RetryTransport` and
  `retry_delay`; the docstring and the "call an HTTP API" recipe name `backoff=1.0` and
  `attempts=1`.
- [ ] The dogfood's `weather.py` will likely trip `raw-httpx-client` or `silent-exit` on its next
  `copier update`.
- [ ] Carried over: the original demo code is at `d8e26b0` for comparison. The gate's pause on
  conflict markers and the conflicted-`pyproject.toml` guard are still proven only by the
  generation tests, not by a consumer update with a real conflict.

From the currency run with sonnet, reviewed in
`~/.claude/plans/review-a-spec-cheeky-octopus.md`. Most valuable first:

- [x] **Bash file writes escaped the edit-time gate**, and nothing ran the tests on work merged
  within the turn. Sonnet wrote 8 of 11 files through heredocs and `sed -i`, as in the geo run.
  The review overstated it: `finish_branch.py` already ran `prek run --all-files` before merging,
  so every file was linted before `main`; only the **tests** were never run. Fixed on
  `fix/finish-branch-tests-and-recovery`: `finish_branch.py` runs the suite after the gate
  (`--no-tests` at this repo's root, whose gate is the suite). **Decided against**, 2026-10-04:
  a `PostToolUse` hook on `Bash` would only move feedback earlier, at a cost on every Bash call;
  and a per-session stop-gate checkpoint (`tools/session_base.py`, built and discarded) closed
  the same test gap with a module and session state where three lines in `finish_branch.py` do.
- [x] **`finish_branch.py` on a dirty tree said "tree is not clean" and nothing else.** It failed
  twice: nothing committed, then a commit the hook aborted after reformatting files, which
  `-q | tail` hid. The error now lists the files and says how to carry on, and names a staged
  file modified since (`MM`/`AM`) as a commit the hook aborted. No `--commit-all` flag: the
  message names the two commands instead.
- [x] **The allowlist omitted `git switch`,** which `CLAUDE.md`'s first rule requires before any
  edit, so every run prompted on its first step. `Bash(git switch:*)`, `Bash(git add:*)` and
  `Bash(git commit:*)` added to `template/.claude/settings.json`; the commit hooks gate commits
  anyway. `python3` left off: its prompt is the one nudge towards Write and Edit, which are gated.
- [ ] **No recipe for a validated argument.** AMOUNT, PAIR and `--margin` were typed `str` and
  checked by a hand-rolled `_usage_error`, giving `<str>` metavars and an ad-hoc message.
  `Annotated[Decimal, typer.Argument(parser=_dec, metavar="AMOUNT")]`, `_dec` raising
  `typer.BadParameter`, exits 2 with "Invalid value for 'AMOUNT': …" (verified on typer 0.27.2).
  A recipe in `SKILL.md` and `reference/typer.md`, and a worked parser with its test in
  `reference/status.py` — a `--timeout`, say.
- [ ] **`examples/currency.md` disagrees with Frankfurter.** It says an unpublished quote is
  absent from `rates`; live, an unknown code is a 404 and `GBP/GBP` a 422. Fix the spec and its
  failure table. In "Recipe: call an HTTP API", one step: run each failure case once against the
  real service and mock what it returns.
- [x] **`reference/test_status.py` patches `status.build_client`**, which the model copied,
  while `CLAUDE.md` says to inject dependencies. `CLAUDE.md` now names it as the one sanctioned
  patch, for a command's end-to-end test through `main`.
- [x] **The `__main__` rule** was read as broken by the reference files. **The review's fix was
  wrong**: `tools/debug_module.py` runs a `src/` module as `python -m`, so relative imports do not
  stop one running, and narrowing the rule would have been a mistake. The modules flagged reach
  their entry point through `cli.py` and have none of their own; one clause in `CLAUDE.md` now
  says so.

Not template problems, per the review: a four-letter test code, a heredoc that broke its own
parentheses, `1e3` echoed as `"1E+3"`, and "check the network" on a 4xx.

### Phase 3 — Make the gate precise and unavoidable

Done on `feat/phase3-gate`, 2026-10-02. The edit-time gate reports failures only, concisely —
`prek --quiet` plus `RUFF_OUTPUT_FORMAT` and `TY_OUTPUT_FORMAT` set to `concise` (ty honours the
variable through `uv check`), 266 bytes where it was 3,048 — and re-runs once when prek only
applied its own fixes. With prek missing it says so to the agent and the user. A `Stop` hook,
`tools/stop_gate.py`, gates every changed and untracked file and runs the tests, blocking once
per stop. `tools/session_doctor.py` reports a missing `prek` or git shim at session start.
Notebook edits are guarded and gated. Every gate and stop-gate run appends a line to `.gate.log`.

The doctor earned its place on its first run in the dogfood, after the `b22dacd` update: it
reported all three git shims missing. They really were, so the update's commit and its merge into
`main` had run no hook at all. `prek run --all-files` had been run by hand before the commit, and
re-run afterwards over the merged range, with the message check on both commits, everything
passed. `prek install` restored the shims. Still unproven on a consumer: a `sed` edit caught by the
stop gate, and a `.gate.log` filling up.

`finish_branch.py` merged the dogfood's one-commit branch unchecked, trusting that its commit had
gone through the hooks. Fixed on `fix/finish-branch-gate`, 2026-10-03: every path now runs
`prek run --all-files` and the `commit-msg` stage (`--commit-msg-filename`) on each message it will
add to `main`, before merging and whatever the shims are doing. The squashed commit is made with
`--no-verify`, so the gate still runs once, not twice. Proven in a generated project with all
three shims deleted: a lint failure and a bad message are both refused, and a clean branch merges.

### Phase 4 — Stabilise the toolchain

Done on `chore/phase4-toolchain`, 2026-10-02. `explicit-preview-rules = true` in both configs, with
ten preview rules selected by code (`PLR1702`, `PLR0914`, `PLW1514`, `PLC2701`, and six bug
detectors), down from 124 by prefix; `no-self-use` is gone. Hook pins bumped to ruff v0.16.10, ty
v0.0.84, rumdl v0.2.78 and uv-pre-commit 0.12.22, with no new findings in any type. pytest names
`strict_config`, `strict_markers`, `strict_xfail` and `strict_parametrization_ids` individually
rather than `strict = true`, which would adopt later options unannounced, and has
`filterwarnings = ["error"]`. Each was probed in a generated project, not just run green.

### Phase 5 — Turn conventions into checks

Done on `feat/phase5-conventions`, 2026-10-02. `check_nested_defs.py` became `check_conventions.py`
plus `convention_rules.py`, hook id `conventions`, with six rules — `nested-def`, `nested-class`,
`complex-comprehension`, `raise-from-none`, `dynamic-attribute` (`getattr`, `setattr`, `delattr`)
and `missing-main-guard` — each with a message naming its fix and a `# noqa: <rule-id>` opt-out.
Five table rows moved from convention to the checker. No template code tripped it; the dogfood
trips it exactly three times, on the `from None` lines noted under phase 1.

A half-added setting now fails `tests/test_config.py`, naming the missed step. The fewer-places
shape was considered: `Settings.model_validate` does read the environment on pydantic-settings
2.15, which would let `load_settings` take `**flags` and drop its keyword list, but only the
constructor is documented as resolving sources, so the four edits stay, guarded by the tests.

### Phase 6 — Cut the always-loaded context; make the skills recipes

Done on `feat/phase6-context`, 2026-10-02 (D3: a script).

- `template/CLAUDE.md` is 165 lines, from 296: the git ritual is a ten-line summary, and the detail
  is a `git-workflow` skill every type ships. `tools/finish_branch.py` runs the procedure —
  squash onto a branch cut from `main`, commit through the full gate, `--no-ff` merge, delete —
  or with `--keep-commits` autosquashes, runs the full gate and merges with `--log`. Tested
  against real git, and end to end under a generated project's real hooks.
- `python-cli-modern` is recipe-first — add a command, call an HTTP API, add a setting — at 116
  lines, with the rationale moved unchanged into nine topic files under `reference/`.
- Reference code: `http_client.py` (per-phase timeouts, User-Agent, retry on 429 and 5xx honouring
  `Retry-After`, idempotent methods only, debug logging) and `status.py`, each with tests. A
  generation test follows the recipe literally — `uv add httpx`, copy, the `cli.py` edit — and runs
  the gate and suite. In place, `.claude/` is excluded from ruff, ty and the conventions hook.
- The machinery's tests are in `tools/tests/`; `tests/` holds the product's, plus a package import
  test every type gets.
- The scaffold docstrings point at the skill's reference files instead of restating the reasons.

Left: the secondary skills' code blocks are still unchecked. Each gets reference files and the
same generation test in its own phase (9–12), as the definition of done there already requires.

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
  generation suite. `prek update` cannot read `template/.pre-commit-config.yaml.jinja`; phase 4 ran
  it in a generated project and copied the revisions back, which a workflow can do too.
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
  spec run.

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
- [ ] **Spec:** one under `examples/` to run — a log or billing-export summariser, say.

### Phase 11 — `tui`

Verified defects in today's setup and skill:

- [ ] The first Pilot test fails with "async def functions are not natively supported": no async
  test plugin ships. Add `pytest-asyncio` to the tui dev group with `asyncio_mode = "auto"`, as
  Textual's testing guide does.
- [ ] `textual console` and `textual run --dev`, which the skill's debugging section depends on,
  come from `textual-dev`, which is not installed. Add it to the tui dev group.
- [ ] Idiomatic Textual fails the gate three ways: `BINDINGS = [...]` trips `mutable-class-default`
  (annotate it `ClassVar[list[BindingType]]`); `compose()` tripped `no-self-use`, which phase 4
  removed; and a handler that ignores its event trips `unused-method-argument` (Textual
  lets a handler omit the event parameter — teach that).
- [ ] The floor is `textual>=7.2.0`, but 8.2.8 is current, a major version on. Re-verify the skill
  against 8.x.

Build-out:

- [ ] **Scaffold:** a single-screen app launched by a `tui` command, its logic in a `domain.py` with
  no Textual import, styles in a `.tcss` file, and a Pilot test at a pinned size.
- [ ] **Debugging recipe:** stepping through the running app with debugpy (a launch line plus the
  existing attach configuration), and through the DebugMCP `pytest` adapter for logic a Pilot test
  reaches.
- [ ] **Spec:** one under `examples/` to run — a log or process viewer, say.

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
- [ ] **Spec:** one under `examples/` to run — a small webhook receiver, say.

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
