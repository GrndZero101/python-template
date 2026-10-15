# TODO

Outstanding work, with enough context to pick up cold in a new session. Rules and workflow live in
[CLAUDE.md](CLAUDE.md); this file is what is *not yet done*, plus the lessons from what is that a
new session would otherwise relearn. The detail of finished work is in `git log`.

## Next up

**Step 9, the uv-script skill.** Step 8 is done (2026-10-15) and Checkpoint C5 reached:
from a session in the canary its hooks, skills, gate and tests work, the secrets audit of its whole
history was clean, its package is renamed and its author email scrubbed, and it is public. The
canary's follow-ups under step 8 are closed, and the update docs now cover both layers. A blank
email can be avoided too: both READMEs show copier's user settings file, filled from `git config`,
and a CLI test pins that such a file cannot split the layers' answers. Next is step 9, the
uv-script skill, then the setup helper planned under "Setup helper", built by following it. Work
runs sequentially, with no worktrees or side tracks. The rest of phase 8 waits behind phase 10 so
that nothing under `template/` moves twice.

The state to expect:

- This repo is the base alone: `template/` and the root `copier.yml`. `tests/test_template.py`
  holds one test, the base alone (about fifteen seconds); `uv run pytest` runs it,
  `prek run --all-files` is the whole gate. Finish a branch with
  `uv run python template/tools/finish_branch.py --no-tests "<type(scope): summary>"`.
- The CLI repo is the sibling directory `../python-template-cli-typer`, seeded from this repo's
  history (a plain clone, so every old hash survives). Its suite (40 tests) generates through the
  CLI template with the base layered on; `BASE_TEMPLATE_DIR` names the base checkout, and without
  it the tests use the base on GitHub. It has no `tools/` and no hooks of its own, by decision: the
  root gate there is prek hygiene, ruff, rumdl and the generation tests.
- Each repo's CI checks the other out (`base/` there, `cli/` here) and ignores that directory in
  `.gitignore`, because copier reads an untracked nested repository as a submodule with no
  `.gitmodules` and fails. This repo's CI runs the CLI suite against the commit under test, which
  is now the only automatic check of the hooks, the licence and the update tests.
- Both repos' `main` are pushed. The CLI repo's CI uses the base's GitHub `main`, so push the base
  first whenever a CLI change depends on a base change. A change that must land in both at once,
  such as a shared question's help text, fails the base's CI whichever goes first: that run checks
  out the CLI's `main` before the CLI half is there. Push the CLI half straight after, then
  `gh run rerun <id> --failed` the base's run (2026-10-16, the blank `author_email`).
- Nothing relies on GitHub's redirect from an old name. The canary is
  `GrndZero101/python-canary-cli-typer`, public since 2026-10-15, at `71af808`. Its history was rewritten
  on 2026-10-15 (step 8), so canary hashes from before that no longer exist anywhere.
  `.copier-answers.yml` names `gh:GrndZero101/python-template-cli-typer` at `ac50467`, and
  `.copier-answers.base.yml` names `gh:GrndZero101/python-template-base` at `07a1f78`. Its package
  is `python_canary_cli_typer`; its script is still `tdf-cli`. The old `template-dogfood` memory
  directory and `~/.claude.json` entries are gone.
- Renaming the directory left the `.venv` pointing at the old path (`Failed to spawn: pytest`):
  `rm -rf .venv && uv sync` fixed it. Any other clone moved on disk needs the same. pytest's
  assertion-rewrite cache (`tests/__pycache__/*-pytest-*.pyc`) also keeps the old path in the
  locations it reports, until `__pycache__` is deleted: cosmetic.

## How work is judged

- **Three goals** (2026-10-02): well-structured DevOps and QOL CLI tools; code a person can
  maintain and step through; and token efficiency — a sonnet-class model builds a good tool
  cheaply because the skills, tooling and hooks carry the knowledge. **Sonnet is the baseline**;
  haiku is an occasional stretch run whose findings are acted on only when the fix is a cheap
  mechanical check that helps any model.
- **Machinery has a budget** (2026-10-04). `tools/` is eleven modules and about 2,000 lines. Add
  a hook, module or stored state only for a defect that actually reached `main`; prefer extending
  an existing check (`finish_branch.py`, the `pre-merge-commit` hook, the stop gate) over a new
  one; and verify a reviewer's claim against the code before acting on it. Two of the currency
  review's seven proposals were wrong on inspection; the 2026-10-15 review's held, bar one
  overstatement and one proposed question that copier's `--skip-tasks` made unnecessary.
- **Prefer a mechanical check, a script or a copyable reference file** to more prose in
  `CLAUDE.md` or a skill. A specific, greppable name in `CLAUDE.md` (`build_client`) steered haiku
  where a docstring pointer did not.
- **Done means**: the generation suite and `prek run --all-files` pass; anything that changes what
  a skill tells a model has been run through a generated project's gate, not just read; and a
  phase that changes what generated projects receive ends with a `copier update` of the canary.
- **Format template code in a generated project before committing.** `template/` is not linted in
  place, so a formatting slip surfaces only in the generation suite, a minute later, at commit.
  Generate a scratch project, copy the file in, `prek run ruff-format`, copy it back.

## Sessions and checkpoints

Decided 2026-10-15. A long session gets slower and costlier per turn and drifts from what is
written down; a fresh one reads only `CLAUDE.md`, memory and this file. So work is cut into
sessions at **checkpoints**, and at each one Claude says so: "Checkpoint: start a new session",
with the next step named in "Next up". Before that it finishes the step, merges it, and updates
this file, which is the hand-off — a fresh session must be able to start from it alone, and a gap
it finds is fixed here first.

A checkpoint falls:

- at the end of any step that ends mergeable, once this file says what comes next;
- after a review is triaged and recorded — the session that made the decisions triages, since it
  holds the evidence, and a fresh one carries them out;
- when the next step needs another working directory: hooks, skills and memory all belong to the
  directory a session started in;
- when `/context` shows the session past about half its window, at the next mergeable point.

Phase 10's checkpoints are named in its steps, C1 to C5. C4 is mandatory, not advisory: the
rename moves the directory the session started in.

## How work runs

Decided 2026-10-15, amended the same day. **Sequential: one session, one branch, one step at a
time.** An earlier plan ran side tracks in git worktrees beside phase 10. It was dropped before
any ran: the author reviews every decision and merge, so a second track mostly adds context
switching; each session pays its own context, against goal 3; two local generation suites slow
each other down; and `finish_branch.py` ends by switching to `main`, which git refuses while
another worktree has it checked out. Phase 10's steps also move the files each next step depends
on. Read-only work — a review, an audit — is still a session started where the files are.

## Status snapshot

- Two copier templates, both **published**: the base at
  [GrndZero101/python-template-base](https://github.com/GrndZero101/python-template-base) and the
  typer CLI at
  [GrndZero101/python-template-cli-typer](https://github.com/GrndZero101/python-template-cli-typer),
  each with `copier.yml` at the root and its files under `template/` via `_subdirectory`. **One
  project shape** (2026-10-05): the typer CLI scaffold. Data processing and full-screen TUIs are
  skills layered on it, not project types.
- **Three recipes ship reference code** that a generation test copies exactly as the recipe says,
  registers in `cli.py` and gates: `python-cli-typer`'s `status`, `python-data`'s `summary`
  (polars, CSV or parquet) and `python-tui`'s `browse` (Textual, Pilot tests).
- `copier update` works and is tested. Every `_task` is guarded with
  `when: "{{ _copier_operation == 'copy' }}"`, or the tasks re-run on update and the commit task
  fails on `no-commit-to-branch`. The variable is `_copier_operation`: `_copier_conf.operation`
  renders undefined, which silently disables every task, copy included.
- `template/` cannot be linted in place (Jinja, no `pyproject.toml`). `tests/test_template.py`
  generates projects and runs their gate and suite; it is the only check on `template/`.
- **CI** (2026-10-15): `.github/workflows/ci.yml` runs the root gate on Linux and the generation
  suite on Ubuntu and macOS on a push to any branch, unless it touches only docs: its `paths` list
  mirrors `generation-tests`' `files:`. Free, since the repo is public. Windows is opt-in since
  2026-10-16, in both repos: `gh workflow run ci.yml --ref <branch> -f windows=true`, at
  milestones and in work aimed at Windows. The targets are Unix-alikes (Linux, macOS, WSL2).
  Warm-cache times: gate 14s, Ubuntu 1m05, macOS 1m43, Windows 7m54; with the CLI suite on
  2026-10-16, Ubuntu 1m26, macOS 4m10, Windows 14m23. Why Windows is that slow is unconfirmed: the
  uv cache is on `D:` and pytest's tmp on `C:`, so uv cannot hardlink and may copy every package
  per project. `--basetemp` on `D:` plus `--durations=15` would test it, in a Windows uplift.
  `prek` is in the root dev group, so CI's version comes from `uv.lock`; with `CI=true` a missing
  tool fails a test rather than skipping it.
- Toolchain: `uv`, `ruff` v0.16.10, `ty` v0.0.84, `prek` 0.5.4, `rumdl` v0.2.78, `copier` 9.17.0.
  Preview rules are selected one by one (`explicit-preview-rules`); pytest names its strict options
  individually and turns warnings into errors.
- `template/tools/`, eleven modules: the hooks `branch_guard` (`PreToolUse`: no edits on `main`),
  `gate` (`PostToolUse`: the gate on every Edit/Write, concise, pausing on conflict markers),
  `stop_gate` (`Stop`: changed files and the tests, measured from the merge-base, blocking once)
  and `session_doctor` (`SessionStart`: status, plus a missing `prek` or git shim);
  `check_conventions` and `convention_rules`, ten rules no linter covers (`nested-def`,
  `nested-class`, `complex-comprehension`, `raise-from-none`, `dynamic-attribute`,
  `missing-main-guard`, `raw-httpx-client`, `patched-httpx`, `silent-exit`, `typer-default`);
  `finish_branch` (squash, full gate, tests, message check, `--no-ff` merge — trusting no hook);
  `gate_log`, `hook_payload`, and the DebugMCP launchers `debug_module` and `debug_pytest`.
- Hooks are **exec form** with `${CLAUDE_PROJECT_DIR}` paths and launch through
  `uv run --no-project --no-config`, so neither a `cd` nor a conflicted `pyproject.toml` breaks
  them. Bash writes (heredocs, `sed -i`) skip the edit-time gate by design; the stop gate and
  `finish_branch.py` are the backstop, and both run the tests. Proven in the canary on
  2026-10-04: a `sed -i` `print` passed the edit-time gate and the stop gate blocked it.
- `cli-modern` ships a **scaffold**, not a demo: an `about` command, global `--verbose`/`--version`,
  a per-command `--output`, each resolving flag, then `<SCRIPT>_*` environment variable, then
  config file, then default through pydantic-settings. `python-cli-typer` is recipe-first — add a
  command, call an HTTP API, a validated argument, add a setting or a secret.
- Agent debugging is the **standalone DebugMCP CLI**, registered per user as `debugmcp-cli`.
  Projects ship `.debugmcp.json`, the two launchers and the `python-debug` skill. Proven headless
  in WSL; neither adapter can pass program arguments, so the skill drives commands through tests.
- **The canary**, the public `GrndZero101/python-canary-cli-typer` (since 2026-10-15, after a
  clean audit, D13): a consumer of both layers with its own `weather` command,
  script `tdf-cli` and package `python_canary_cli_typer`. Its author email, in its answers and in
  every commit, is the GitHub noreply address. **Drive it from a session started in
  its own directory**: Claude Code loads hooks and skills from the session's project, so from here
  they are all inert. A rehearsal on a scratch clone (`_src_path` edited,
  `copier update --trust --defaults --vcs-ref <branch>`) predicts a real update exactly. After an
  update, `session_doctor` may report missing git shims;
  `prek install -t pre-commit -t commit-msg -t pre-merge-commit` restores them.

## Decisions

Open:

| # | Decision | Needed by | Recommendation |
|---|---|---|---|
| D5 | Tagging, which changes `copier update` semantics | Phase 8 | Stay untagged until the canary settles, then `v0.1.0`. See phase 8. |

Decided:

- **D1** — `.python-version` rendered from the answer, 3.12–3.14, default 3.14.
- **D2** — spec runs by hand, sonnet the baseline, reviewed by Opus (see "Spec runs").
- **D3** — the git ritual is a script, `finish_branch.py`.
- **D4** (2026-10-05, replacing 2026-10-04) — `cli-stdlib` is its own repo, not a type here. A
  scaffold built for it on 2026-10-05 is parked on the local branch `archive/cli-stdlib`
  (`4098f9e`) to seed that repo; delete the branch once it has.
- **D6** (2026-10-05) — `data` and `tui` are recipe-first skills layered on the CLI, shipped to
  every project, not project types. **D7** (their order) is moot.
- **D8** (2026-10-04) — the config file lives in `~/.config/<script>/` on macOS as on Linux,
  `XDG_CONFIG_HOME` honoured on every platform, `%APPDATA%` on Windows.
- **D9** (2026-10-04) — a data command's JSON emits secrets raw, as `terraform output -json` and
  `gh auth token` do, via an explicit `.get_secret_value()`; incidental exposure — repr, logs,
  whole-model dumps such as `about` — is masked by `SecretStr`, as `gh auth status` and
  `kubectl config view` mask. Checked: pydantic-settings masks `repr` and
  `model_dump(mode="json")`.
- **D10** (2026-10-04) — the config file is YAML, for flexibility as configs grow.
- **D11** (2026-10-05) — **one project shape.** `project_type` branched `copier.yml`,
  `pyproject.toml`, the README and the tests, and the three unbuilt types' skills rotted unexercised
  (every one broke on a first attempt). Why not layer directories for two CLI scaffolds: `_exclude`
  matches rendered paths, so same-named modules needed Jinja-named directories, which the
  2026-10-05 attempt showed to be unreadable. Superseded across repos by D12.
- **D12** (2026-10-15) — **layered templates.** A shared base template plus one thin template per
  use case, applied to the same project with separate answers files, as copier documents. A spike
  with two local templates proved it: one `copier copy` of the use case produced both layers, its
  task running `copier copy` of the base; the base read the use case's answers through
  `_external_data`; `copier update -a .copier-answers.base.yml` and a plain `copier update` each
  touched only their own layer; a local edit survived. **No update chain**: a project records both
  sources, so a base fix reaches it without a use-case release. The costs: an update is two
  commands, each needing a clean tree; a file both layers render conflicts (proven — markers in
  `pyproject.toml`), so ownership must be disjoint and checked; only ruff can extend a base-owned
  config, so pytest, ty and rumdl config and the dev group repeat in each use case's
  `pyproject.toml` (D15); and the base's CI must run every use case's suite. Rules split as
  `CLAUDE.md` (base) plus `.claude/rules/<use case>.md`, which Claude Code loads at the same
  priority. Rejected: copying `tools/` per repo (drift), and vendoring the base into each use case
  as a subtree (a real update chain).
- **D13** (2026-10-15) — **names, and no redirects.** This repo becomes `python-template-base`;
  use cases are `python-template-cli-typer` (today's scaffold), `-cli-stdlib`, `-api-fastapi`, and
  `js-template-web-vue` for the Vue front end in `~/tmp/operator/inventory-app-design-spec.md`.
  uv scripts with PEP 723 metadata are a **skill in the base**, not a repo. The skill
  `python-cli-modern` becomes `python-cli-typer`. Each use case gets a public
  `python-canary-<use case>`; the base gets `python-canary-base` only once it has the uv-script
  skill to exercise. The sole user is the author, so renames break cleanly: every reference is
  updated, and nothing may rely on GitHub's redirect from an old name. "Dogfood" is retired for
  corporate use. The local directory moves too, and with it the Claude Code memory directory,
  which is keyed on the path.
- **D14** (2026-10-15) — **licence is a question.** `template/LICENSE` ships "Copyright (c) 2026
  GrndZero101" literally, so every generated project names the template's author. The base asks
  `license` (MIT default, Apache-2.0, Proprietary) and `copyright_holder` (default `author_name`;
  not git config, which copier can read only through an extension each user must install), and
  records the year at generation. That takes both halves of copier's "lock a computed value"
  recipe, because a `when: false` answer is otherwise dropped from the answers file and
  recomputed on every update: `default: "{{ copyright_year | default('%Y' | strftime) }}"`, and
  the answers-file template dumping
  `{{ dict(_copier_answers, copyright_year=copyright_year) | to_nice_yaml }}`. Checked: copier
  9.17 loads `strftime` by default.
- **D15** (2026-10-15) — **the base on its own, and in a brownfield repo.** The base is a use case
  in itself: a skeleton with every guard for prototyping before the shape is known, or dropped
  into a brownfield repo with the least disruption. The 2026-10-15 review's proposed answers were
  each checked against the code, and accepted unamended.

  **Who owns `pyproject.toml`.** The use case, when layered. The base renders a minimal one under
  `_skip_if_exists`, which copier never overwrites and leaves out of the update patch, for the
  standalone and brownfield cases — so the ownership check exempts it. Ruff is the only tool that
  merges configs: the use case writes `extend = "ruff-base.toml"` and then **only additive keys**
  (`extend-select`, `extend-per-file-ignores`, `extend-exclude`), because its own `select` or
  `per-file-ignores` would replace the base's lists, dropping the whole rule set and the `tools/**`
  exemptions. pytest, ty and rumdl take the first config file they find and merge nothing, so a
  base-owned `pytest.ini`, `ty.toml` or `.rumdl.toml` would lock every use case and brownfield repo
  out of adding a setting (FastAPI's async tests need their own); their config stays in
  `pyproject.toml`, guarded by the contract test in phase 10.

  **Order, and the shared questions.** Keep the spike's: one `copier copy` of the use case, whose
  only task runs `copier copy --trust --defaults` of the base, and the base owns every bootstrap
  task. The base defines the shared questions (author, licence, Python version) with
  `default: "{{ _external_data.use_case.<key> | default('') }}"`, so layered under `--defaults` it
  asks nothing, and standalone it asks everything; a missing answers file yields an empty dict.
  The base's source is an answer in the use case (`base_template`, default
  `gh:GrndZero101/python-template-base`), so the generation tests and the base's CI can point it at
  a local checkout. The base's `copier.yml` sets `_answers_file: .copier-answers.base.yml`, so no
  `-a` is needed. Cost: shared questions are defined twice; a generation test asserts both
  answers files agree on them.

  **Applying the base to an existing repo** (the canary, a brownfield repo). It is a `copy`, so
  every task runs: `git init`, `uv sync`, `git add -A`, `git commit` on whatever branch is checked
  out, and the `prek install`s. `copier copy --skip-tasks` (`-T`) avoids it, followed by the three
  `prek install`s by hand. A `bootstrap_git` question only if brownfield adoption becomes real.
  "Generation into unusual git states" — a destination that is already a repo, a default branch
  other than `main` — belongs here, not in phase 8.

  **Brownfield gating.** `finish_branch.py` runs `prek run --all-files` (finish_branch.py:209), and
  `ty` checks the whole project whatever files it is given (gate.py:20–23), so the edit-time and
  stop gates would fail a legacy codebase at the first save too. No machinery now: brownfield has
  not reached `main`. When it does: a `--changed-only` flag on `finish_branch.py` reusing
  `stop_gate.changed_files`, and `exclude` lists in the ty and rumdl config the adopter can edit.

## Done: phases 1–9, and the lessons that still apply

Phases 1–6 (2026-10-02 to 10-04) fixed the defects a review reproduced at `712a7f8`, then made the
gate concise and unavoidable, stabilised the toolchain, turned conventions into checks, cut
`template/CLAUDE.md` from 296 lines to about 170, and made the skills recipes. Phase 7 added
secrets, the config file and the install story; phase 9 made data and TUI layered skills; phase 8
put this repo under CI. The detail is in `git log`.

- **The edit-time gate's report** is `prek --quiet` with ruff and ty set to concise output: 266
  bytes where it was 3,048. A repeated convention message prints once, then only its location.
- **`finish_branch.py` trusts no hook.** A commit made while the shims were missing ran none, and
  a rebase runs none, so it runs the full gate, the tests and the message check itself.
- **A half-added setting fails `tests/test_config.py`**, naming the missed step. `load_settings`
  keeps its explicit keywords: only the `Settings` constructor is documented to resolve sources.
- **A new global option needs no command edit**: commands take `GlobalOptions` whole and required.
  The canary proved the earlier per-command wiring leaked — its `weather.py` accepted `--config`
  and ignored it — and, after the fix, that a stale call fails `ty` with an error that alone leads
  to the fix.
- **Convention messages route the model to the skill**: `raw-httpx-client`, `patched-httpx` and
  `silent-exit` each name the reference file to copy. That reached haiku, which never loaded the
  skill on its own.
- **pydantic-settings has no runtime path for `YamlConfigSettingsSource`**, and that source lets a
  list-shaped file escape as a bare `ValueError`, so `config_file.py` parses with `yaml.safe_load`.
- **An editable `uv tool install` keeps its old `--version`** until `--reinstall`; a plain one is a
  snapshot that `uv tool upgrade` rebuilds from its source.
- **Library facts the skills now encode**: registering a polars frame in duckdb needs `pyarrow`;
  duckdb's integer `sum` is `Decimal(38, 0)`; a positional `scan_csv(schema=)` silently mislabels
  swapped columns; loguru's sink bypasses Textual's stderr redirect, so the app logs with
  `self.log`; rich's `err.print` wraps errors at the console width and reads `[...]` as markup, so
  commands write errors with `sys.stderr.write`.
- **`pytest.raises(match=)` is a regex**: `repr()` of a Windows path is full of escapes. CI's first
  run caught it on Windows only; the reference tests `re.escape` it. Windows runners check out
  with `core.autocrlf=true`, as users' Git for Windows does, and nothing broke on CRLF.
- **Decided against**, 2026-10-04: a `PostToolUse` hook on `Bash`, and a per-session stop-gate
  checkpoint (`tools/session_base.py`, built and discarded). The gap they targeted — tests never
  run on work merged within a turn — took three lines in `finish_branch.py`.

## Spec runs

Resumed 2026-10-05 for the layered skills. By hand, as `examples/README.md` in the CLI repo
describes — a fresh project, the spec handed unedited to sonnet, the gate and tests run by hand,
then a review in a separate `opus` session in plan mode driven by `examples/evaluate.md` there. Each
template finding becomes an item here, checked against the code first. Rerun both specs after any
phase that changes what a skill or the gate tells a model; the fixes from the currency run — the
validated-argument recipe, the corrected spec, `finish_branch.py` running the tests — are not yet
measured.

| Date | Spec | Model | Template | Gate | Tests | `/cost` | Verdict and main findings |
|---|---|---|---|---|---|---|---|
| 2026-10-03 | geo | haiku | `354b24f` | pass | 215 pass | 68 calls, 26k out | Two required tests wrong or missing. Never loaded `python-cli-modern`: hand-rolled `httpx.Client()`, patched httpx in every test, no response model, cause dropped on exit. |
| 2026-10-03 | geo | sonnet | `354b24f` | pass | 212 pass | 9 calls, 10k out | Meets every row. Loaded the skill second, copied `http_client.py`, `MockTransport` throughout. Wrote every file through one heredoc. |
| 2026-10-03 | geo | haiku | `f6c03ff` | pass | pass | 68 calls, 31k out | Close. Found `build_client` through `CLAUDE.md` and copied it. Still never loaded the skill: parsed the response by hand, reported `exc.request.url` instead of the cause. |
| 2026-10-03 | currency | sonnet | `2b06886` | pass | 276 pass | 15 requests, 17.7k out, $0.65 | Meets the spec, every value a `Decimal`. Branched unprompted, `Annotated` throughout. 8 of 11 writes were Bash; validated arguments by hand as `str`; mocked a "missing key" the service answers with a 404; `finish_branch.py` failed twice on a dirty tree. All seven findings acted on. |
| 2026-10-05 | spend | sonnet | `73933c1` | pass | 283 pass | 14 calls, 35k out | Meets the spec. Loaded `python-data` first, unprompted, then `python-cli-modern`; branched first; left the work on its branch and said so. Every write was Bash, so only the stop gate ran. Read columns by name, sidestepping the skill's positional `scan_csv(schema=)` — fixed. Three fix rounds, none template defects: `ty` on `Series.sum()`'s broad return type, `PLR0917`/`PLR0913` on a seven-parameter command (`*` and a commented `noqa`), and a rich title wrapping at 80 columns under a substring assert. |
| 2026-10-05 | logs | sonnet | `15ed246` | pass | pass | 10 calls, 32k out | Meets the spec. Loaded `python-tui` unprompted; branched first; finished with `finish_branch.py`. Every write was Bash. Logic outside the app, `.tcss` styles, letters typed in search tested not to fire bindings. Patched its own `run_screen` seam in the command tests — beyond `CLAUDE.md`'s one sanctioned patch, and it said so: the reference had no seam, so the skill could not show how to test a picker through `main`. Fixed: `run_screen` is in the reference and named beside `build_client`. |

What the runs taught: the skill's content works and its discovery is weak below sonnet; sonnet
writes through Bash as a habit, so the backstops matter more than the edit-time gate; and specs and
API docs are unreliable about failures, so the recipe now says to provoke each one live.

Open from the runs:

- [ ] The gate's pause on conflict markers and the conflicted-`pyproject.toml` guard are proven
  only by generation tests, never by a consumer update with a real conflict. The `7a5941e` and
  `2957d4c` canary updates had none; still watching.
- [ ] **Watch, from the `spend` run** — act on a second occurrence, each a line in a skill: a
  command with more than five parameters trips `PLR0913` and `PLR0917`, and the answer is
  keyword-only flags plus a commented `noqa`; polars' `Series.sum()` is typed as a broad union, so
  `ty` wants `int(...)` before it reaches an `int` parameter; and a test asserting a substring of a
  rich table breaks when the title wraps at 80 columns.
- [ ] **Declare each setting once**, if a run shows a model fumbling "Recipe: add a setting". Today
  a setting is declared four times — `Settings`, `_Overrides`, a `GlobalOptions` field or
  `load_settings` keyword, an option alias — and `load_settings` copies each flag by hand. Building
  `given` from `dataclasses.asdict(options)` plus the keywords, dropping `None`, deletes
  `_Overrides` and the copy lines: three edits instead of four, and two wiring tests in
  `test_config.py` go. Bundle with it: the app callback and each command both call
  `load_settings`, so every run parses the environment and reads the config file twice; the
  callback needs only `verbose`. Found 2026-10-05. Judged not worth changing: the unused `err`
  console, `config.py` importing rich through `output.py`, and five docstring lines over 100
  columns.

## Phase 10 — Base and use-case layers

Prove D12 on the use case that already works before building another. One session at a time, in
order; each step ends mergeable, and the checkpoints say where a new session starts. Rehearse
each step on scratch copies first; the canary's update is the acceptance test.

1. [x] **Settle D15**: accepted unamended (2026-10-15) and moved to "Decided".
   **Checkpoint C1**, reached.
2. [x] **Assign every file an owner**, done by directory (2026-10-16). `template/` and the root
   `copier.yml` are the base; `use-cases/cli-typer/` (its own `copier.yml` and `template/`) is the
   CLI layer, and step 6 lifts it out with its history. The owners are in the root `CLAUDE.md`.
   Notes a fresh session needs:
   - `.claude/rules/cli-typer.md` does not exist yet. Step 3 creates it, in
     `use-cases/cli-typer/template/.claude/rules/`, with the rows it moves out of the base.
   - The skill rename is done: `python-cli-modern` is `python-cli-typer` everywhere but the
     spec-run table, which is history.
   - `ruff-base.toml` holds all of ruff's rules as a top-level file (`[lint]`, not
     `[tool.ruff.lint]`). `target-version` stays in each `pyproject.toml`, because it follows the
     project's Python floor. The use case adds only `extend-immutable-calls` for typer.
   - The base shares four questions, not three: `project_name` as well, because its fallback
     `pyproject.toml` needs a name. Only `project_name` has a validator, as the others were
     optional before the split.
   - The use case's `base_template` defaulted to `gh:GrndZero101/python-template` until step 7
     renamed the repo; it is now `gh:GrndZero101/python-template-base`.
   - The update tests build their templates with `_snapshot`: a use case is a subdirectory, which
     copier cannot update from, so each test copies it into a throwaway git repo. The snapshot
     includes uncommitted changes, so the tests no longer see only committed state.
   - New tests: each layer writes its own answers file; the use case keeps the `pyproject.toml` it
     wrote; each layer updates only its own files (D12's claim); the base alone passes its gate.
3. [x] **Neutralise base-owned text that names the CLI** (2026-10-16). The typer and httpx rows
   and the sanctioned-patches sentence moved from the base `CLAUDE.md` to
   `use-cases/cli-typer/template/.claude/rules/cli-typer.md`; the `convention_rules.py` messages
   point at `.claude/skills/*/reference/` rather than a named skill, and `silent-exit`'s message
   covers stdlib logging as well as loguru. A generation test keeps those names out of the base.
4. [x] **The mechanical checks** (2026-10-16), in `tests/test_template.py` under "the contract
   between the layers": the layers render no file in common but the base's `_skip_if_exists`; the
   two `copier.yml` files define every base question alike (type, help, choices) and the generated
   answers files agree; and the `pyproject.toml` of the use case and of the base alone both hold
   what the base relies on. The ruff keys forbidden beside `extend` are `select`, `ignore`,
   `per-file-ignores` and `unfixable`, not just the first two D15 named: each replaces a base
   list. Each check was shown to fail when its rule was broken.
5. [x] **Licence questions** (D14, 2026-10-16). Both `copier.yml` files ask `license` (MIT,
   Apache-2.0, Proprietary) and `copyright_holder`, and compute `copyright_year`; both
   answers-file templates write the year back, so an update keeps it (a test edits the recorded
   year to 1999 and checks the update leaves it). `template/LICENSE` is `LICENSE.jinja`, holding
   the three texts, the Apache one verbatim from the Apache Software Foundation's text (found in
   an installed package, not typed from memory). Both `pyproject.toml.jinja` files gain
   `license = "<SPDX>"` (`LicenseRef-Proprietary` for Proprietary), and `uv build` accepts all
   three. The README's licence line follows the answer. The root `LICENSE` stays MIT: it is this
   repo's own.
   **Checkpoint C2**, reached: steps 2–5 are merged here, and the layering is rehearsed by the
   update tests and by scratch generations.
6. [x] **New repo `python-template-cli-typer`**, public (read "Before step 6" below first). Done:
   both CIs green.
   **Seed it from this repo's history** —
   clone, then remove base-owned files — never `git init`: `copier update` re-renders the old
   template at the commit recorded in the canary's answers file, and that commit must exist in the
   new repo. CI on three platforms against the base at `HEAD`; the base's CI checks it out and runs
   its generation suite against the base commit under test, through `base_template`.
   **Checkpoint C3**, reached.
7. [x] **Rename** (D13): this repo to `python-template-base` on GitHub, the local directory, the
   remote URL and the Claude Code memory directory; then every reference to the old name. Done
   2026-10-15: the author renamed the repo, directory and remote by hand; the memory was copied
   across and the old project directory deleted; both repos' references followed, the bootstrap
   commit message becoming `chore: generate project from python-template-base` and the root dev
   project `python-template-base-dev`.
   **Checkpoint C4, mandatory**: the session's directory no longer exists. Reached.
8. [x] **Migrate the canary** to two answers files. Done 2026-10-15, C5 included. What the run
   showed:
   - Both copier commands took `--skip-tasks --defaults`. `--defaults` answers the questions added
     since `2957d4c` (`license` MIT, `copyright_holder` the author, `base_template`), so `LICENSE`
     now names Timothy Longbottom, not GrndZero101.
   - Step 1 conflicted only on the README's "Generated from" line; the template's side is right.
   - Between the steps `.gitignore` is gone, so `.gate.log` and `__pycache__` show as untracked:
     `git add -A` only after step 2. Commit nothing in between either, since the hooks' config is
     gone too.
   - The rehearsal and the real run matched file for file (35 files, +190 −138); afterwards a
     plain update and a base update were both no-ops. The base update's `MissingFileWarning` for
     `.copier-answers.yml` comes from copier rendering the old base in a temp directory: harmless.

   The plan, as followed. **Order matters**: `copier update` deletes every file the old render had
   and the new one lacks, with no check for local edits (`_remove_old_files`, still so in copier
   9.18). So:
   1. Edit `_src_path` in `.copier-answers.yml` to the CLI repo — the one sanctioned edit of a file
      that says never to edit it — and `copier update`. The canary's edits to `cli.py`,
      `pyproject.toml` and `README.md` merge; every base-owned file is deleted.
   2. `copier copy --trust --skip-tasks <base> .`, which recreates them at the base's `HEAD`;
      the canary never edited them, so nothing is lost. Then the three `prek install`s by hand.

   The reverse order deletes the base again. Step 1 deletes `.claude/settings.json` and `tools/`,
   so run the migration by hand or from a session outside the canary, never inside it. Rehearse
   on a scratch clone. Then rename the repo to `python-canary-cli-typer`. Make it public only
   after a secrets audit of its whole history: read-only, from a session in its directory.
   **Checkpoint C5**: a new session started in the canary, to confirm its hooks, skills, gate
   and tests. Reached 2026-10-15, and the canary made public the same day:
   - All four hooks fire and block: the branch guard refused a Write on `main`; on a probe branch
     the edit-time gate and the stop gate both blocked a `print` and a nested `def`. Skills load,
     the gate is green (bar `no-commit-to-branch`, which always fails on `main`), and the suite
     passes (272, one skip).
   - The secrets audit was clean: all 28 commits then, every ref, by pattern with no scanner
     installed — token shapes, secret-named literals, credentialed URLs, sensitive file names,
     long literals, IPs. GitHub held no issues, PRs, Actions runs or releases. The only personal
     data was the author's two email addresses.
   - **The package rename** (D13) was two user-run updates that change answers only:
     `copier update --trust --defaults --vcs-ref=:current: --data package_name=... --data
     project_name=... --data project_description=...`, then the base with
     `-a .copier-answers.base.yml --data project_name=...`, which changed only its answers file.
     No conflicts, but `_remove_old_files` bites here too: each template file under `src/<package>/`
     is rendered at the new path and the old one deleted, edits and all. `cli.py` silently lost the
     `weather` registration — no marker, no `.rej`. Project-only modules (`weather.py`,
     `http_client.py`) stayed in the old directory, their tests importing the old name. After
     `uv sync` the `tdf-cli` script was missing, probably because the old and new distributions
     both own it and removing the old took it; `uv sync --reinstall-package <new>` restored it.
   - **The email scrub**, because the author wants no personal address in the canary:
     `author_email` became the GitHub noreply address through the same kind of update on both
     layers. The history was rewritten with `git filter-repo` (`--mailmap`, `--replace-text`,
     `--replace-message`) on a fresh clone, verified — no address in any object, the tip's tree
     identical — and pushed to a deleted and recreated GitHub repo, since a force-push leaves old
     commits reachable by hash. The author ran the rewrite, the delete and the push: an agent's
     auto mode refuses history rewriting.

   Follow-ups the canary found:
   - [x] ~~**Document renaming a project**~~ — dropped 2026-10-16. The canary's rename was part of
     the restructuring, and the pain makes a rename rare enough not to document. Looking at the
     sync docs for it found the real gap instead, fixed the same day: a generated CLI project's
     README updated only the use case, never the base, and the base README still described the
     CLI. Both now give the two-layer update flow.
   - [x] **A blank `author_email`** rendered `email = ""` in `pyproject.toml`. Fixed 2026-10-16 in
     both repos: the key is left out when the answer is blank, the question's help (identical in
     both `copier.yml`s, as a CLI test requires) suggests GitHub's noreply address, and each suite
     has a test generating with a blank email.
   - [x] **`finish_branch.py` drops commit bodies when it squashes**: the canary's rename lost its
     explanation. Fixed 2026-10-15: the squashed commit is MESSAGE, then each commit's body in
     order (a repeated paragraph once), then their trailers once each as the last paragraph, where
     git reads them. The merge commit keeps the subject alone. Reaches the canary on its next base
     update.
9. [ ] **Later in the phase**: the uv-script skill, written directly in the base after the split —
   `tests/test_template.py:24–31` asserts the exact skill set, so a draft before the split would
   collide with it — then `python-canary-base` to exercise it; seed `python-template-cli-stdlib`
   from `archive/cli-stdlib`.

### Before step 6

What the 2026-10-16 session learned that step 6 depends on. Settle the first two with the author
before moving a file.

1. **How the new repo is gated.** The root of this repo borrows the base: its
   `.claude/settings.json` hooks and its `conventions` hook run `template/tools/*.py`, and its
   `CLAUDE.md` imports `@template/CLAUDE.md`. The new repo has none of those files. D12 rejected
   copying `tools/` per repo (drift), so the options are a root gate with no tools at all (prek
   hygiene, ruff, rumdl and the generation tests only), or fetching the base's `tools/` at a pinned
   commit. Decide first; it shapes the new repo's `CLAUDE.md`, hooks and pre-commit config.
2. **Where `examples/` and the spec-run material go.** `examples/` and "Spec runs" below test a
   model building CLIs on the typer scaffold, so they belong with the CLI repo, but `TODO.md`
   stays here. Moving them is a call about where the benchmark lives.
3. **Seed by plain clone, never `git filter-repo`.** filter-repo rewrites every hash, and the point
   of seeding from history is that the canary's recorded `_commit` (an old, single-template
   commit) must still exist. A clone keeps the hashes: clone, `git rm` the base-owned files, move
   `use-cases/cli-typer/*` to the root in one commit, point `origin` at the new repo. Old commits
   keep the old layout, which is what `copier update` re-renders at step 8.
4. **The base must be on GitHub first.** The use case's `base_template` defaults to
   `gh:GrndZero101/python-template` (the name until step 7), and the new repo's CI needs the base
   at `HEAD`. `main` was pushed on 2026-10-16; push again if it has moved before the first CI run.
5. **Splitting `tests/test_template.py`.** Tests of the base alone (the base passes its own gate,
   its questions are defined in the use case) stay here. Everything generated through the use case
   moves, with `USE_CASE_DIR` becoming the repo root and the base coming from an environment
   variable naming a checkout (default: the GitHub URL). The three contract tests need both
   templates, so they run in the CLI repo's suite and this repo's CI runs that suite against the
   base commit under test (checkout the CLI repo, set the variable, `uv run pytest`). The helpers
   `_snapshot`, `_snapshot_base` and `_snapshot_use_case` copy a template into a throwaway git repo
   because copier cannot update from a subdirectory; in the CLI repo the use case is a git root,
   so it can be cloned directly.
6. **CI.** Copy `.github/workflows/ci.yml` (actions pinned by SHA, `fetch-depth: 0`, git identity in
   the environment) and add a second `actions/checkout` of the base into `base/`. Its `paths:`
   filter must list what `generation-tests` lists. The Windows and macOS jobs are the only check of
   the portability rules, so do not trim the matrix. (Superseded 2026-10-16: Windows is opt-in.)
7. **Leftovers named for step 7.** The base's bootstrap commit message, the `base_template`
   default, `tests/` assertions on "python-template" and the README's Path A (which says to clone
   and copy the use case) all change with the rename or the split. All done in step 7.

## Setup helper (after step 9)

Raised 2026-10-16. One command takes a machine from nothing to ready, and later keeps it current:
`uv`, the tools, copier's settings, and both layers' updates of a project. Two files, because the
first step has to run before anything is installed and everything after it is easier in Python.
Not a template file: it runs before any project exists, so it lives at this repo's root and is
linted by the root gate.

**The shim: a POSIX `sh` script, as thin as it can be.** Its only job is a `uv` it can trust:

1. **No `uv` on PATH:** say so, and with consent (`--yes` when there is no TTY; refuse otherwise)
   run the official installer, `curl -LsSf https://astral.sh/uv/install.sh | sh`, falling back to
   `wget -qO-`. Then use `$HOME/.local/bin/uv` by absolute path for the rest of the run, since
   PATH in this process has not changed.
2. **`uv self update --dry-run`, exit code non-zero:** stop. Exit 2 means this `uv` cannot update
   itself — Homebrew, pip, a distro package, or a second copy shadowing the standalone one; the
   error says which (seen 2026-10-16: "Self-update is only available for uv binaries installed via
   the standalone installation scripts", plus "Are multiple copies of uv installed?"). Print it,
   and how to move to the standalone install (`brew uninstall uv`, then step 1). A network failure
   also lands here: stop and say the check could not run. A `uv` older than 0.7.3 has no
   `--dry-run` and errors on the flag: treat it as outdated.
3. **Exit 0 with "Would update uv from vX to vY":** outdated. Offer `uv self update`; stop if
   declined. "You're on the latest version" passes. Matching that text is the one fragile part:
   the shim's tests must run against the real latest `uv` on CI so a reworded message fails there.
4. **Hand off:** `exec uv run --script <helper> "$@"`. From a clone, `<helper>` is the file beside
   the shim; piped from the web, a `raw.githubusercontent.com` URL at the same pinned ref as the
   shim, which `uv run` accepts.

Hard means hard: no `--skip-uv-check`. The helper may then assume a current standalone `uv`. Never
`set -o pipefail` or `[[ ]]`, `local` or arrays: `/bin/sh` is `dash` on Ubuntu (and on the
author's WSL) and macOS's `sh` is bash in POSIX mode, so CI covers both.

**The helper: a `uv run` script with PEP 723 inline metadata.** `requires-python` and its
dependencies in the header, plus `[tool.uv] exclude-newer` so a run months later resolves the same
versions. Subcommands, each re-runnable:

- `doctor`: report, change nothing. `uv` (already gated), `copier` and `prek` as uv tools and
  their versions, git identity, copier's settings file, `gh` installed and authenticated.
- `setup`: `uv tool install` or `uv tool upgrade` copier and prek; write copier's settings file
  from `git config`, offering the GitHub noreply address from `gh api user` (`id` and `login`)
  when `gh` is authenticated, since its default token cannot read a private email. Never
  overwrite a settings file without showing the diff and asking.
- `new <dir>`: `copier copy --trust` from the CLI template, after `doctor` passes.
- `update`: in a project, the README's two-layer flow — clean tree, branch, `copier update`, `uv
  sync`, commit, the base the same way, then `tools/finish_branch.py`. Stops at a conflict and
  says how to resume. The flow is spelled out in both READMEs, so this replaces prose a user had to
  follow by hand.

It is held to the template's own rules (no `print`, a stderr logger, functions small enough to
step through), so it is a real example of the uv-script skill from step 9: build the skill first,
then this by following it.

**Open:**

- Names for both files: corporate-neutral, and the subcommand name a user will type often.
- Typer and rich as dependencies, or stdlib `argparse` to keep the first run's download small.
- `copier` as a uv tool the helper drives, or as a library in the helper's own environment. A
  tool keeps the READMEs' commands true; a library allows `user_defaults` without a settings file.
- Hosting: run from a clone only, or also `curl … | sh` at a pinned ref. The second needs a tag
  (phase 8's tagging) or a commit in the URL, never `main`.

**Tests:** shellcheck with `--shell=sh` in the root gate. The shim's four branches tested with a
stub `uv` on PATH that prints each case, plus one test against the real `uv` on CI. The helper's
subcommands tested with `git`, `gh` and copier stubbed or pointed at a tmp directory; `update`
end-to-end in the CLI repo's suite, which already has projects to update.

## Phase 8 — CI, releases and updates (after phase 10)

Done: CI for this repo (2026-10-15), under "Done" above.

- [ ] **CI shipped in generated projects**: `prek run --all-files` and `uv run pytest`, so a
  generated tool is checked away from its author's machine too. Base-owned, so it waits only so
  that nothing under `template/` moves twice. **A consumer's private repo pays for it**: a Free
  account has 2,000 minutes a month, and Windows and macOS burn the quota faster, macOS at about
  ten times Linux. Ship Linux only, with Windows and macOS commented in; run on pushes to `main`
  and on pull requests, not on every branch push.
- [ ] **Pin automation.** Nothing bumps the hook pins or the dependency floors, and they drifted
  10–20 releases in two months. After the split the hook pins live in the base's config and the
  floors in each use case. A scheduled `prek update` workflow, or Renovate, gated by the
  generation suite. `prek update` cannot read `template/.pre-commit-config.yaml.jinja`; phase 4 ran
  it in a generated project and copied the revisions back, which a workflow can do too.
- [ ] **Tagging** (D5), one tag series per repo. **Once any tag exists, `copier update` moves to
  the latest PEP 440 tag rather than `HEAD`** unless given `--vcs-ref HEAD` — right for stable
  releases, wrong while iterating, because fixes stop reaching the canary until tagged. Stay
  untagged until the canary settles, then cut `v0.1.0`. The README's example now pins a commit.
- [ ] **Per-release update notes.** The README's "Keeping it in sync" covers the update mechanics.
  A release should also say what a conflict never will: which features were absorbed from
  consumers (`typer_entrypoint.py` superseded the canary's own version, with changed semantics),
  and which interface moves a consumer's own commands must follow (`-v/--verbose` went global, so
  `tdf-cli weather -v cleve` became `tdf-cli -v weather cleve`, and nothing warned).

## Later

- **The Textual console**, attached through `TEXTUAL=devtools,debug`, is unverified by hand. The
  mechanism is read from `textual_dev/cli.py`; it needs two real terminals to see.
- **DebugMCP on Windows native.** The agent-session half is done in WSL. Still unverified, and
  needing a session started on Windows itself: the `cmd /c` registration, `uv` resolving as the
  adapter command, and both adapters launching through it, including the `python` adapter's
  launcher, proven so far only on Linux. CI proved on 2026-10-15 that the exec-form hooks' `uv`
  and `git` resolve there. Known CLI gaps, worked around in the skill rather than fixed: it ignores
  `launch.json`; it always sets `program`, so pytest and every `src/` module need a launcher, and it
  cannot pass program arguments; complex values render as dunder trees unless wrapped in `repr()`;
  the debuggee's output and logpoint output are not captured.
- **The DebugMCP VS Code extension.** Deferred by choice. It drives VS Code's own debugger over
  HTTP on `localhost:3001` and reuses `launch.json`, but uses the interpreter selected for the
  *open window*: from a `python-template` window it launched the system Python and failed to import
  the package. Open: two windows contending for one port, and coexisting with the CLI, since
  `debugmcp configure` keeps a single `debugmcp` entry.
