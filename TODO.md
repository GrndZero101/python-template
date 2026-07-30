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

### 3. Promote the config to `~/.claude`

The original plan said to wait for real use before promoting. That condition is now met.

Promote: `CLAUDE.md`, `.claude/settings.json`, `.claude/skills/`.
Leave per-repo: `pyproject.toml`, `.pre-commit-config.yaml`, `tools/check_nested_defs.py`.

Check first that the `PreToolUse` branch guard behaves in a repo whose default branch is not
`main`, and in a directory that is not a git repository at all — the hook currently assumes both.

## Decisions still open

### What is this repo?

It is named `claude`, the package is `src/claude/`, and it now holds three real CLI tools plus a
toolchain. Three readings, each implying different next steps:

- **Template** to clone for new Python work → rename the package, strip the tools back to examples,
  write the README that explains how to use it.
- **Real project** that happens to have good tooling → the toy commands should go.
- **Sandbox** for tuning Claude Code config → promotion (item 3) is the whole point and the tools
  are scaffolding.

### `whoami` shadows the system command

`[project.scripts]` installs a `whoami` that masks the OS one on `PATH`. Flagged early, never
decided. Rename, or accept it.

## Nice to have

- **Exercise the untested skills.** `python-fastapi`, `python-tui` and `python-data` have never
  been run against real work. Only `python-cli`, `python-cli-stdlib` and `python-cli-modern` have.
- **Gate instrumentation.** Append pass/fail from the `PostToolUse` hook to a gitignored `.gate.log`
  to get a hard count of how often the gate catches something. Lower value now the guardrail test
  has already passed.
- **`mcp-debugger` trial.** Worth it only if inspecting live state starts beating adding log lines.
- **Commit summary length is unenforced.** `conventional-pre-commit` validates format but not the
  72-character rule, which stays a convention. A custom `commit-msg` check could close it, but that
  would be a second piece of custom code — the bar is "prove no native tool does it" first.
