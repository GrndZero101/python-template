# TODO

Outstanding work, with enough context to pick up cold in a new session. Rules and workflow live in
[CLAUDE.md](CLAUDE.md); this file is what is *not yet done*, plus the lessons from what is that a
new session would otherwise relearn. The detail of finished work is in `git log`.

## Next up

In order.

1. **Spec runs** for the two layered skills, on sonnet, by hand as
   [examples/README.md](examples/README.md) describes: `spend` (`python-data`) and `logs`
   (`python-tui`), both written 2026-10-05. A fresh project receives both skills, so each run
   also shows whether the model picks the right one unprompted.
2. Phase 8.

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
  review's seven proposals were wrong on inspection.
- **Prefer a mechanical check, a script or a copyable reference file** to more prose in
  `CLAUDE.md` or a skill. A specific, greppable name in `CLAUDE.md` (`build_client`) steered haiku
  where a docstring pointer did not.
- **Done means**: the generation suite and `prek run --all-files` pass; anything that changes what
  a skill tells a model has been run through a generated project's gate, not just read; and a
  phase that changes what generated projects receive ends with a `copier update` of the dogfood.
- **Format template code in a generated project before committing.** `template/` is not linted in
  place, so a formatting slip surfaces only in the generation suite, a minute later, at commit.
  Generate a scratch project, copy the file in, `prek run ruff-format`, copy it back.

## Status snapshot

- A working copier template, **published** at
  [GrndZero101/python-template](https://github.com/GrndZero101/python-template): `copier.yml` at the
  root, the generated project under `template/` via `_subdirectory`. **One project shape**
  (2026-10-05): the typer CLI scaffold. Data processing and full-screen TUIs are skills layered on
  it, not project types; `copier copy gh:GrndZero101/python-template <dest>` is verified end to end.
- **Three recipes ship reference code** that a generation test copies exactly as the recipe says,
  registers in `cli.py` and gates: `python-cli-modern`'s `status`, `python-data`'s `summary`
  (polars, CSV or parquet) and `python-tui`'s `browse` (Textual, Pilot tests).
- `copier update` works and is tested. Every `_task` is guarded with
  `when: "{{ _copier_operation == 'copy' }}"`, or the tasks re-run on update and the commit task
  fails on `no-commit-to-branch`. The variable is `_copier_operation`: `_copier_conf.operation`
  renders undefined, which silently disables every task, copy included.
- `template/` cannot be linted in place (Jinja, no `pyproject.toml`). `tests/test_template.py`
  generates projects and runs their gate and suite; it is the only check on `template/`.
- Toolchain: `uv`, `ruff` v0.16.10, `ty` v0.0.84, `prek`, `rumdl` v0.2.78, `copier` 9.17.0.
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
  `finish_branch.py` are the backstop, and both run the tests. Proven in the dogfood on
  2026-10-04: a `sed -i` `print` passed the edit-time gate and the stop gate blocked it on
  `ruff-check` and `pytest`; both hooks wrote `.gate.log`, the stop gate as `stop-gate`.
- `cli-modern` ships a **scaffold**, not a demo: an `about` command, global `--verbose`/`--version`,
  a per-command `--output`, each resolving flag, then `<SCRIPT>_*` environment variable, then
  default through pydantic-settings. `python-cli-modern` is recipe-first — add a command, call an
  HTTP API, a validated argument, add a setting — with reference code (`http_client.py`,
  `status.py`) that a generation test copies exactly as the recipe says and gates.
- Agent debugging is the **standalone DebugMCP CLI**, registered per user as `debugmcp-cli`.
  Projects ship `.debugmcp.json`, the two launchers and the `python-debug` skill. Proven headless
  in WSL; neither adapter can pass program arguments, so the skill drives commands through tests.
- **The dogfood**, `GrndZero101/template-dogfood`: a private `cli-modern` consumer with its own
  `weather` command and script `tdf-cli`, at `7a5941e` (2026-10-05), the single-shape merge:
  as rehearsed, no conflicts, the two layered skills added and `project_type` dropped from the
  answers. The `a7c49b5` update before it brought in secrets, the config file and `GlobalOptions`;
  two updates were the evidence for the last: the first left `weather.py` ignoring `--config`; the
  second, after `GlobalOptions`, failed ty on the old call and the error alone led to the fix.
  **Drive it from a session started in its own directory**: Claude Code loads hooks and skills
  from the session's project, so from here they are all inert. A rehearsal on a scratch clone
  (`_src_path` edited, `copier update --trust --defaults --vcs-ref <branch>`) predicts a real
  update exactly. After the `b22dacd` update `session_doctor` found all three git shims missing;
  `prek install -t pre-commit -t commit-msg -t pre-merge-commit` restored them.

## Decisions

Open:

| # | Decision | Needed by | Recommendation |
|---|---|---|---|
| D5 | Tagging, which changes `copier update` semantics | Phase 8 | Stay untagged until the dogfood settles, then `v0.1.0`. See phase 8. |

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
  (every one broke on a first attempt). FastAPI is a separate project. Why not layer directories
  for two CLI scaffolds: `_exclude` matches rendered paths, so same-named modules needed
  Jinja-named directories, which the 2026-10-05 attempt showed to be unreadable.

## Done: phases 1–6, and fixes from the spec runs

Phases 1–6 (2026-10-02 to 10-04) fixed the defects a review reproduced at `712a7f8`, then made the
gate concise and unavoidable, stabilised the toolchain, turned conventions into checks, cut
`template/CLAUDE.md` from 296 lines to about 170, and made the skills recipes. Lessons that still
apply:

- **The edit-time gate's report** is `prek --quiet` with ruff and ty set to concise output: 266
  bytes where it was 3,048. A repeated convention message prints once, then only its location.
- **`finish_branch.py` trusts no hook.** A commit made while the shims were missing ran none, and
  a rebase runs none, so it runs the full gate, the tests and the message check itself.
- **A half-added setting fails `tests/test_config.py`**, naming the missed step. `load_settings`
  keeps its explicit keywords: only the `Settings` constructor is documented to resolve sources.
- **Convention messages route the model to the skill**: `raw-httpx-client`, `patched-httpx` and
  `silent-exit` each name the reference file to copy. That reached haiku, which never loaded the
  skill on its own.
- **Bugbear's `B008` advice is wrong for typer**, so `typer.Argument` and `typer.Option` are in
  `extend-immutable-calls` and `typer-default` gives the `Annotated` fix instead.
- **httpx ignores proxy variables once given a transport**, so `build_client` routes through
  `EnvironmentProxyTransport`. Its retry `backoff=` exists for APIs with a rate policy.
- **Decided against**, 2026-10-04: a `PostToolUse` hook on `Bash`, and a per-session stop-gate
  checkpoint (`tools/session_base.py`, built and discarded). The gap they targeted — tests never
  run on work merged within a turn — took three lines in `finish_branch.py`.

## Spec runs

Resumed 2026-10-05 for the layered skills. By hand, as [examples/README.md](examples/README.md)
describes — a fresh project, the spec handed unedited to sonnet, the gate and tests run by hand,
then a review in a separate `opus` session in plan mode driven by
[examples/evaluate.md](examples/evaluate.md). Each template finding becomes an item here, checked
against the code first. Rerun both specs after any phase that changes what a skill or the gate
tells a model; the fixes from the currency run — the validated-argument recipe, the corrected
spec, `finish_branch.py` running the tests — are not yet measured.

| Date | Spec | Model | Template | Gate | Tests | `/cost` | Verdict and main findings |
|---|---|---|---|---|---|---|---|
| 2026-10-03 | geo | haiku | `354b24f` | pass | 215 pass | 68 calls, 26k out | Two required tests wrong or missing. Never loaded `python-cli-modern`: hand-rolled `httpx.Client()`, patched httpx in every test, no response model, cause dropped on exit. |
| 2026-10-03 | geo | sonnet | `354b24f` | pass | 212 pass | 9 calls, 10k out | Meets every row. Loaded the skill second, copied `http_client.py`, `MockTransport` throughout. Wrote every file through one heredoc. |
| 2026-10-03 | geo | haiku | `f6c03ff` | pass | pass | 68 calls, 31k out | Close. Found `build_client` through `CLAUDE.md` and copied it. Still never loaded the skill: parsed the response by hand, reported `exc.request.url` instead of the cause. |
| 2026-10-03 | currency | sonnet | `2b06886` | pass | 276 pass | 15 requests, 17.7k out, $0.65 | Meets the spec, every value a `Decimal`. Branched unprompted, `Annotated` throughout. 8 of 11 writes were Bash; validated arguments by hand as `str`; mocked a "missing key" the service answers with a 404; `finish_branch.py` failed twice on a dirty tree. All seven findings acted on. |

What the runs taught: the skill's content works and its discovery is weak below sonnet; sonnet
writes through Bash as a habit, so the backstops matter more than the edit-time gate; and specs and
API docs are unreliable about failures, so the recipe now says to provoke each one live.

Open from the runs:

- [ ] The gate's pause on conflict markers and the conflicted-`pyproject.toml` guard are proven
  only by generation tests, never by a consumer update with a real conflict. The `7a5941e` dogfood
  update had none; still watching.
- [ ] The original demo code is at `d8e26b0`, for comparing against what a run builds.
- [ ] **Declare each setting once**, if a run shows a model fumbling "Recipe: add a setting". Today
  a setting is declared four times — `Settings`, `_Overrides`, a `GlobalOptions` field or
  `load_settings` keyword, an option alias — and `load_settings` copies each flag by hand. Building
  `given` from `dataclasses.asdict(options)` plus the keywords, dropping `None`, deletes
  `_Overrides` and the copy lines: three edits instead of four, and two wiring tests in
  `test_config.py` go. Bundle with it: the app callback and each command both call
  `load_settings`, so every run parses the environment and reads the config file twice; the
  callback needs only `verbose`. Found 2026-10-05; both predate phase 7's stdlib work. Judged not
  worth changing: the unused `err` console, `config.py` importing rich through `output.py`, and
  five docstring lines over 100 columns.

## Phase 7 — DevOps CLI features

- [x] **Secrets** (D9), 2026-10-04. "Recipe: add a secret setting": `SecretStr`, environment
  only (no flag), unwrapped at the point of use, sent in a header since URLs are logged.
  `secret_fields()` in `config.py` exempts secrets from the flag wiring tests; a credential-named
  field not typed `SecretStr` fails first under `-x`, so a model is not steered into adding a
  flag; an `about` test, skipped until a secret exists, asserts masking in table, JSON and log.
  Verified by applying the recipe in a generated project, both wrongly and rightly.
- [x] **A config-file layer** (D8, D10), 2026-10-04. `config_file.py`: flag, then variable, then
  `config.yaml`, then default. `config` is itself a setting (`--config`, `<PREFIX>_CONFIG`), which a
  custom source reads from `current_state` after the init and env sources — pydantic-settings has
  no runtime path for `YamlConfigSettingsSource`, and that source lets a list-shaped file escape
  as a bare `ValueError`, so the file is parsed with `yaml.safe_load` (`pyyaml` declared
  directly). Unknown keys, non-mappings, bad YAML and a missing named file each fail naming the
  file; a secret's value is masked in validation errors. `conftest.py` points `XDG_CONFIG_HOME`
  into `tmp_path`. The dogfood's update proved the per-command wiring leaked: its own `weather.py`
  accepted `--config` and ignored it. Fixed 2026-10-05 by passing `GlobalOptions` whole and
  required — `load_settings(global_options(ctx), output=...)` — so a new global option needs no
  command edit, and a command that omits it fails `ty` and raises `TypeError`.
- **The `cli-stdlib` scaffold** moved out (D4): its own repo, seeded from `archive/cli-stdlib`.
- [x] **An install story in the generated README**, 2026-10-04: "Installing it" (`uv tool
  install .`, `--editable`, from git or a tag, `update-shell`, upgrade and uninstall by package
  name) and "Releasing a version" (`uv version --bump` on a branch, `finish_branch.py`, tag the
  merge). Verified in a generated project. An editable install keeps its old `--version` until
  `--reinstall`; a plain one is a snapshot that `uv tool upgrade` rebuilds from its source.

## Phase 8 — CI, releases and updates

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
- [ ] **Tagging** (D5). The template has **no git tags**, so `.copier-answers.yml` records a bare
  commit hash and the `--vcs-ref v1.3.0` examples in the README refer to tags that do not exist.
  **Once any tag exists, `copier update` pulls to the latest tag rather than `HEAD`** — right for
  stable releases, wrong while iterating, because fixes stop reaching the dogfood until tagged.
  Stay untagged until the dogfood settles, then cut `v0.1.0` and fix the README examples.
- [ ] **Per-release update notes.** The README's "Keeping it in sync" covers the update mechanics.
  A release should also say what a conflict never will: which features were absorbed from
  consumers (`typer_entrypoint.py` superseded the dogfood's own version, with changed semantics),
  and which interface moves a consumer's own commands must follow (`-v/--verbose` went global, so
  `tdf-cli weather -v cleve` became `tdf-cli -v weather cleve`, and nothing warned).
- [ ] **Generation into unusual git states**, a natural CI job. Unverified: a destination that is
  already a git repo, and one whose default branch is not `main` (`branch_guard` takes
  `--protected main master`); the generation tasks assume `git init -b main` succeeds.

## Phase 9 — Layered skills (done 2026-10-05)

- [x] **`project_type` removed** (D11). A generated project differs from one made at `c08a7d0`
  only in shipping `python-data` and `python-tui` and in its answers file.
- [x] **`python-data`**: "Recipe: add a data command" with `reference/summary.py`. Fixed the
  verified defects — `fetchone()[0]` failed ty, `LazyFrame.profile()` deprecated since 1.43 — and
  re-verified against polars 1.44 and duckdb 1.5, which found two more: registering a polars frame
  needs `pyarrow`, and duckdb's integer `sum` arrives as `Decimal(38, 0)`.
- [x] **`python-tui`**: "Recipe: add a TUI command" with `reference/rows.py` (no Textual import)
  and `reference/browse.py`. Fixed the verified defects — no async test plugin, no `textual-dev`,
  `BINDINGS` without `ClassVar`, a skill written for Textual 7 — and found that loguru's sink
  bypasses Textual's stderr redirect, so the app logs with `self.log`. `TEXTUAL=devtools,debug`
  reaches the console through the project's own script, since `textual run --dev` needs an app it
  can build without arguments.
- [x] **Reference commands write errors with `sys.stderr.write`**, as the scaffold does: rich's
  `err.print` wrapped them at the console width, splitting the path a test looked for, and would
  read `[...]` in a path or message as markup.
- [x] **Specs**, 2026-10-05: `examples/spend.md` and `examples/logs.md`.
- [ ] **A sonnet run of each**, recorded under "Spec runs".
- [ ] **Unverified by hand:** the Textual console attached through `TEXTUAL=devtools,debug`. The
  mechanism is read from `textual_dev/cli.py`; it needs two real terminals to see.

## Later

- **DebugMCP on Windows native.** The agent-session half is done in WSL. Still unverified, and
  needing a session started on Windows itself: the `cmd /c` registration, `uv` resolving as the
  adapter command, and both adapters launching through it, including the `python` adapter's
  launcher, proven so far only on Linux. Phase 8's CI covers whether the exec-form hooks' `uv` and
  `git` resolve there. Known CLI gaps, worked around in the skill rather than fixed: it ignores
  `launch.json`; it always sets `program`, so pytest and every `src/` module need a launcher, and it
  cannot pass program arguments; complex values render as dunder trees unless wrapped in `repr()`;
  the debuggee's output and logpoint output are not captured.
- **The DebugMCP VS Code extension.** Deferred by choice. It drives VS Code's own debugger over
  HTTP on `localhost:3001` and reuses `launch.json`, but uses the interpreter selected for the
  *open window*: from a `python-template` window it launched the system Python and failed to import
  the package. Open: two windows contending for one port, and coexisting with the CLI, since
  `debugmcp configure` keeps a single `debugmcp` entry.
- **The generation tests are not offline.** `uv sync` runs during generation and reaches the
  network on a cold cache. Everything else about them is deterministic.
