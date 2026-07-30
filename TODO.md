# TODO

Outstanding work, with enough context to pick up cold in a new session.
Rules and workflow live in [CLAUDE.md](CLAUDE.md); this file is only what is *not yet done*.

## Status snapshot

- Toolchain: `uv`, `ruff`, `ty`, `prek`, `rumdl`, plus one custom check
  (`tools/check_nested_defs.py` — no linter covers `def` inside `def`).
- Guards live: `PreToolUse` blocks edits on `main`, `no-commit-to-branch` blocks direct commits,
  `conventional-pre-commit` checks every message, `SessionStart` reports branch and tree state.
- Six skills under `.claude/skills/`: `python-cli`, `python-cli-stdlib`, `python-cli-modern`,
  `python-data`, `python-fastapi`, `python-tui`.
- Three commands: `publicip`, `whoami`, `geo get-coordinates`.
- The `geo` build was a deliberate test of whether the guardrails let a cheaper model self-correct.
  It passed: no `noqa`, no `type: ignore`, no `Any`, no new per-file-ignores, and the skills
  demonstrably steered (`logging_setup.py` and `typer_entrypoint.py` are both prescribed by
  `python-cli-modern`, not obvious inventions).

## Do next

### 1. Land `refactor/modern-cli-stack`

One commit (`780efc2`), converts `publicip` and `whoami` to the typer/httpx/pydantic/rich/loguru
stack so all three commands match. Gate and tests were green on the branch.

```bash
git switch refactor/modern-cli-stack
git rebase main                    # trivial: one commit
prek run --all-files               # required after any rebase — no hooks run during one
git switch main
git merge --no-ff refactor/modern-cli-stack
git branch -d refactor/modern-cli-stack
```

### 2. Document the merge-message convention

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

### 3. Convert this repo into a project template

**Decided: template, not global promotion.** Promoting `CLAUDE.md`, settings and skills to
`~/.claude` was the earlier plan and has been dropped. The two are competing designs, and
per-project wins: a repo-local `CLAUDE.md` makes a project self-describing to any agent, on any
machine, for any collaborator, and survives being cloned. Global config gives none of that. Keep
`~/.claude` for genuinely personal preferences only.

Tooling: **copier** (`uv tool install copier`, 9.17.0 verified). `uv` has no template mechanism —
there is no `uv init --template`. Copier is chosen over cookiecutter for one reason: `copier update`
re-applies template changes to *already-generated* projects, so improvements to CLAUDE.md or a skill
can be pulled downstream instead of being stranded in whichever repo they were written in.

Work needed:

- `copier.yml` asking: package name, project name, description, author, and **project type**. The
  type maps onto the existing two-axis skill design — `cli-stdlib`, `cli-modern`, `fastapi`, `tui`,
  `data` — and conditionally ships the matching skill, dependencies and lint config (e.g. `"FAST"`
  added to `select` only for FastAPI).
- Parameterise the package name. It is currently `claude` in `src/claude/`, which is wrong for
  every generated project.
- Decide what is infrastructure and what is example. `publicip`, `whoami` and `geo` are
  demonstrations, not things a new project wants.
- Templated files use Jinja; the `.jinja` suffix convention keeps the source repo itself runnable.
- Verify the `PreToolUse` branch guard survives generation into a repo whose default branch is not
  `main`, and into a directory that is not yet a git repository at all — the hook currently assumes
  both.

### 4. Trial `mcp-debugger`

[debugmcp/mcp-debugger](https://github.com/debugmcp/mcp-debugger) — 138 stars, actively maintained
(last push 2026-07-27), drives `debugpy` over DAP for breakpoints, stepping, variable inspection and
expression evaluation.

TypeScript, so it needs Node — which cuts against the Python preference, but this is a dev tool, and
`ruff`/`prek`/`rumdl` are already Rust. The Python alternatives are all far less maintained:
`dap_mcp` (40 stars, last push 2025-09), `mcp-debugpy` (8 stars, 2025-11).

Worth trialling because all of CLAUDE.md's debuggability rules exist to make step-debugging possible,
and that capability currently goes unused by the agent that has to follow them.

## Decisions still open

### `whoami` shadows the system command

`[project.scripts]` installs a `whoami` that masks the OS one on `PATH`. Flagged early, never
decided. Rename, or accept it.

## Nice to have

- **Exercise the untested skills.** `python-fastapi`, `python-tui` and `python-data` have never
  been run against real work. Only `python-cli`, `python-cli-stdlib` and `python-cli-modern` have.
- **Gate instrumentation.** Append pass/fail from the `PostToolUse` hook to a gitignored `.gate.log`
  to get a hard count of how often the gate catches something. Lower value now the guardrail test
  has already passed.
- **Commit summary length is unenforced.** `conventional-pre-commit` validates format but not the
  72-character rule, which stays a convention. A custom `commit-msg` check could close it, but that
  would be a second piece of custom code — the bar is "prove no native tool does it" first.
