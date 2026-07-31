# TODO

Outstanding work, with enough context to pick up cold in a new session.
Rules and workflow live in [CLAUDE.md](CLAUDE.md); this file is only what is *not yet done*.

## Status snapshot

- Toolchain: `uv`, `ruff`, `ty`, `prek`, `rumdl`. Four modules under `tools/`:
  `check_nested_defs` (no linter covers `def` inside `def`), `branch_guard` and `gate` (the two
  hooks), and `hook_payload` (shared parsing so they cannot diverge).
- Guards live: `PreToolUse` blocks edits to *repo* files on `main`, `no-commit-to-branch` blocks
  direct commits while still permitting `--no-ff` merges, `conventional-pre-commit` checks every
  message, `SessionStart` reports branch and tree state.
- **Every hook is a single executable invocation, no shell operators** — the portability rule.
  The edit-time gate runs `prek run --files <edited>`, so it and the commit-time gate are the
  same list by construction rather than two lists that can drift.
- Six skills under `.claude/skills/`: `python-cli`, `python-cli-stdlib`, `python-cli-modern`,
  `python-data`, `python-fastapi`, `python-tui`.
- **One console script, `cli`**, with two subcommands on the typer/httpx/pydantic/rich/loguru
  stack: `cli geo <location>` and `cli currency <amount> <PAIR>`. Shared plumbing in
  `output.py` (two consoles, `CLI_OUTPUT`), `logging_setup.py`, `typer_entrypoint.py`.
  85 tests, all offline via `httpx.MockTransport`.
- `mcp-debugger` is installed and **proven** against `geo`. Node LTS 24.18.0 via winget,
  `@debugmcp/mcp-debugger` 0.23.0 global, `debugpy` a dev dependency, server registered at
  **user scope** so nothing ships yet. It confirmed CLAUDE.md's central claim empirically: a
  module-level helper was called from a breakpoint with invented literal arguments
  (`render_places_json([Place.model_validate({...})])`), which a nested `def` makes impossible.
  Injected `client` inspected fine; `Place(...)` reprs in four fields where the raw dict
  truncated mid-key through `place_id`/`licence`.
- The `geo` build was a deliberate test of whether the guardrails let a cheaper model
  self-correct. It passed: no `noqa`, no `type: ignore`, no `Any`, no new per-file-ignores, and
  the skills demonstrably steered.

## Do next

### 1. Document the merge-message convention

The only rule in this repo written down **nowhere** — not in CLAUDE.md, not in the enforcement
table — and predictably the only one that has already drifted: `ea8131f` used git's default
`Merge branch 'feat/geo-get-coordinates'` instead of a descriptive conventional subject.

Add a short subsection to `## Merging` covering:

- Squash path (one commit): merge subject repeats the conventional summary; body carries anything
  the branch commit does not say. Do not manufacture prose when there is nothing to add.
- Rebase path (several commits): merge subject summarises the branch, and `git merge --no-ff --log`
  populates the body with what arrived.
- `Refs: #N` trailer once there is a remote and PRs exist. Footers are part of the Conventional
  Commits spec; branch names are not, and git stores them nowhere.

### 2. Convert this repo into a project template

**Decided: template, not global promotion.** Promoting `CLAUDE.md`, settings and skills to
`~/.claude` was the earlier plan and has been dropped. The two are competing designs, and
per-project wins: a repo-local `CLAUDE.md` makes a project self-describing to any agent, on any
machine, for any collaborator, and survives being cloned. Global config gives none of that. Keep
`~/.claude` for genuinely personal preferences only.

Tooling: **copier** (`uv tool install copier`, 9.17.0 verified). `uv` has no template mechanism —
there is no `uv init --template`. Copier is chosen over cookiecutter for one reason: `copier update`
re-applies template changes to *already-generated* projects, so improvements to CLAUDE.md or a skill
can be pulled downstream instead of being stranded in whichever repo they were written in.

**How the template stays testable** — this is copier's own documented answer to "placeholders make
the repo unrunnable": `_subdirectory`. The repo root stops being a Python project and holds only
template metadata; everything that becomes a generated project lives one level down.

```text
copier.yml              # _subdirectory: template
tests/test_template.py  # generates into tmp, then runs the generated project's own gate
template/               # <- becomes the new project
  pyproject.toml.jinja  # needs substitution
  CLAUDE.md             # literal copy — no placeholders, stays real
  tools/                # literal copies — still lintable, still testable
  src/{{ package_name }}/
```

Only files needing substitution take the `.jinja` suffix, so `branch_guard.py`,
`check_nested_defs.py` and every skill remain ordinary files.

Work needed:

- `copier.yml` asking: package name, project name, description, author, and **project type**. The
  type maps onto the existing two-axis skill design — `cli-stdlib`, `cli-modern`, `fastapi`, `tui`,
  `data` — and conditionally ships the matching skill, dependencies and lint config (e.g. `"FAST"`
  added to `select` only for FastAPI).
- `_tasks` for the side effects: `git init -b main`, `uv sync`, and **all three** prek shims
  (`prek install && prek install -t commit-msg && prek install -t pre-merge-commit`). Ship
  `pyproject.toml.jinja` in full rather than calling `uv init` — the ~110 lines of ruff/ty/rumdl
  config are the entire value, and `uv init` emits a stub with none of it.
- Parameterise the package name. It is currently `claude` in `src/claude/`, which is wrong for
  every generated project.
- Decide what is infrastructure and what is example. `cli geo` and `cli currency` are
  demonstrations. Keeping **one** is probably right — a template with zero example code gives a
  new project nothing to pattern-match against.
- Test with [pytest-copie](https://github.com/12rambau/pytest-copie) (22 stars, active): generate
  into a tmp dir, then run `prek run --all-files` and `pytest` *inside the generated project*.
  That is the only test that proves anything; `copier-template-tester` checks rendering alone.
  Prior art worth reading first: [mjun0812/python-copier-template](https://github.com/mjun0812/python-copier-template).
- Verify the `PreToolUse` branch guard survives generation into a repo whose default branch is not
  `main` (it takes `--protected main master`), and into a directory that is not yet a git
  repository at all.
- Decide whether `mcp-debugger` moves from user scope into the template. It is currently user-only
  precisely because project scope would force **Node 22+ onto every generated Python project**.
  `debugpy` is already a dev dependency, so the Python half travels regardless.
- `copier update` needs the generated project to be a git repo with a **clean tree**, and depends
  on the `.copier-answers.yml` written at generation. Do not delete that file.

## Nice to have

- **Exercise the untested skills.** `python-fastapi`, `python-tui` and `python-data` have never
  been run against real work. Only `python-cli`, `python-cli-stdlib` and `python-cli-modern` have.
- **Gate instrumentation.** Append pass/fail from the `PostToolUse` hook to a gitignored `.gate.log`
  to get a hard count of how often the gate catches something. Lower value now the guardrail test
  has already passed.
- **Commit summary length is unenforced.** `conventional-pre-commit` validates format but not the
  72-character rule, which stays a convention. A custom `commit-msg` check could close it, but the
  bar is still "prove no native tool does it first".
