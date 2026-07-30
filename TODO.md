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
- Three commands, all on the typer/httpx/pydantic/rich/loguru stack: `publicip`, `whoami`,
  `geo get-coordinates`.
- The `geo` build was a deliberate test of whether the guardrails let a cheaper model self-correct.
  It passed: no `noqa`, no `type: ignore`, no `Any`, no new per-file-ignores, and the skills
  demonstrably steered (`logging_setup.py` and `typer_entrypoint.py` are both prescribed by
  `python-cli-modern`, not obvious inventions).

## Do next

### 1. Trial `mcp-debugger` — do this before deleting anything

Time-sensitive: item 2 removes `publicip` and `whoami`, and the template work eventually strips
the example code back. Once that happens there is nothing left to set a breakpoint in, and a
debugger tested against a hello-world proves nothing.

`geo` is the right subject. It has an injected httpx client, a rate limiter and pure parsing
functions — exactly the shape CLAUDE.md's debuggability rules exist to produce. Confirming that a
breakpoint can be set and an injected dependency inspected **validates the premise of the whole
ruleset**, which has never actually been checked because the agent has never had a debugger.

[debugmcp/mcp-debugger](https://github.com/debugmcp/mcp-debugger) — Node 22+, drives `debugpy`
over DAP, works on Windows, ~18 tools (`set_breakpoint`, `get_stack_trace`, `get_variables`,
`step_into`, `evaluate_expression`). Install via `npm install -g @debugmcp/mcp-debugger`, or the
repo's `scripts/install-claude-mcp.sh`. The `stdio` argument is required or the protocol corrupts.

### 2. Restructure to a single `cli` with two subcommands

Target shape, replacing three separate console scripts:

```text
cli geo <location>          # existing, keep
cli currency <args>         # new
```

Delete `publicip` and `whoami`. `whoami` also shadows the OS command, which closes that open
decision by deletion rather than by choosing a name.

`currency` demonstrates FX conversion and margin calculation — e.g. the spread between the
interbank rate and a quoted rate. API is **Frankfurter**, no auth, no User-Agent restriction:

```text
https://api.frankfurter.dev/v1/latest?base=GBP&symbols=AUD,USD,EUR
https://api.frankfurter.dev/v1/2026-01-15?base=GBP&symbols=AUD    # historical
https://api.frankfurter.dev/v1/2026-01-01..2026-01-10?base=GBP    # time series
https://api.frankfurter.dev/v1/currencies                          # supported list
```

Response shape: `{"amount":1.0,"base":"GBP","date":"2026-07-30","rates":{"AUD":1.9179}}`.

Two traps worth knowing before starting:

- **`api.frankfurter.app` 301-redirects to `api.frankfurter.dev/v1/`.** httpx does **not** follow
  redirects by default, unlike requests, so the old domain fails with a bare 301 rather than
  working. Use the `.dev` host directly, or set `follow_redirects=True` deliberately.
- **Money is not a float.** Rates come back as JSON numbers; conversions and margin arithmetic
  belong in `decimal.Decimal`, with rounding stated explicitly. This is the one place a
  demonstration CLI can be subtly, invisibly wrong.

### 3. Document the merge-message convention

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

### 4. Convert this repo into a project template

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

## Nice to have

- **Exercise the untested skills.** `python-fastapi`, `python-tui` and `python-data` have never
  been run against real work. Only `python-cli`, `python-cli-stdlib` and `python-cli-modern` have.
- **Gate instrumentation.** Append pass/fail from the `PostToolUse` hook to a gitignored `.gate.log`
  to get a hard count of how often the gate catches something. Lower value now the guardrail test
  has already passed.
- **Commit summary length is unenforced.** `conventional-pre-commit` validates format but not the
  72-character rule, which stays a convention. A custom `commit-msg` check could close it, but the
  bar is still "prove no native tool does it first".
