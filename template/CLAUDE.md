# Python rules

Enforced by a PostToolUse hook that auto-formats, then blocks on anything left. Violations block
the edit — fix them, don't work around them. A Stop hook checks every file the branch has changed
again, and runs the tests, before a turn can end, so a file changed by `sed` or a heredoc, or
already committed, is caught too.

## Structure

- **Never define a function inside another function.** The only exception is a decorator or factory
  that *returns* the inner function. Helpers go at module level, named `_helper`.
  *Why: a nested def cannot be breakpointed by name or called from pdb with literal arguments, and
  its closure state is invisible in the debugger's Variables pane.*
- Guard clauses over nesting. Return or raise early; at most 3 levels of nested blocks.
- At most ~40 statements, complexity 8, 12 locals and 5 arguments per function. Past that it is
  more than one function.
- Don't define a class inside a function either.
  *Why: same reason, plus a fresh type object per call breaks `isinstance` and pickling.*
- One responsibility per module. Several small modules beat one large one.
  *Why: an agent re-reads whole files; small files mean cheaper, more accurate edits.*

## Debuggability

Every rule here exists so a human can stop the program and inspect it.

- Name intermediate values. No comprehension with more than one `for`, and no nested
  comprehensions — use an explicit loop when there is logic worth inspecting.
  *Why: a breakpoint on a comprehension chain has nothing to hover over.*
- Dataclass, `NamedTuple` or `TypedDict` over ad-hoc dicts for structured data.
  *Why: a dict renders as an opaque blob; a dataclass has a readable `repr`.*
- No lambda beyond a trivial attribute or index access.
  *Why: it shows as `<lambda>` in stack traces with no source context.*
- Inject dependencies — clock, rng, HTTP client, paths — as parameters with defaults. Never reach
  for module-level mutable state. The sanctioned patches: a command's end-to-end test through
  `main` replaces `<module>.build_client`, or a TUI command's `<module>.run_screen`, with
  `monkeypatch.setattr` — the one thing each command builds rather than takes as a parameter.
  *Why: a function must be re-runnable in isolation from a breakpoint, with values you choose.*
- Never swallow an exception. `raise ... from e`, or `logger.exception(...)` — never
  `raise ... from None`, which discards the cause just as surely. That includes an exit:
  `raise typer.Exit(1) from e` on its own still swallows `e`, because nothing prints an exit's
  cause. Name `e` in the error message and log it too.
  *Why: a bare `except: pass` destroys the traceback that tells you where it started.*
- Diagnostics go to a configured logger writing to **stderr**; data goes out with
  `sys.stdout.write`. Never `print`, not even in a `__main__` block. Stdlib `logging` by default;
  `loguru` where a stack skill says so.
  *Why: stdout is reserved for a command's data, so it stays pipeable. Diagnostics that land there
  corrupt the output a caller is parsing.*
- Every module that can run standalone gets `if __name__ == "__main__":`. A command module reached
  only through `cli.py` has no entry point of its own, and needs none.

## Agent-friendliness

- Explicit over dynamic. No `getattr` dispatch, no metaclass tricks, no runtime-generated
  attributes.
  *Why: these defeat grep and breakpoints alike — the two ways code gets navigated.*
- Full type annotations on every public signature.
- Errors name the fix: `raise ValueError(f"expected .json, got {path.suffix}; pass a JSON file")`.
- Tests are deterministic: seed randomness, freeze time, no network.

## Portability

Everything here must run unchanged on **Windows native** and on **Unix-alikes** — Linux, macOS,
and containers, which are Linux. This is a template; a generated project may land anywhere.

- **`pathlib`, never string paths or `os.path`.** Path containment and comparison are
  case-insensitive and separator-agnostic on Windows, case-sensitive with `/` on POSIX.
  `pathlib` gets both right with no branching; hand-rolled string logic gets one of them wrong.
- **Explicit `encoding="utf-8"`** on every read and write. The default encoding is UTF-8 on
  Linux and macOS and locale-dependent on Windows, so omitting it is a latent decoding bug.
- **No POSIX-only modules** — `pwd`, `grp`, `fcntl`, `termios` — outside a guarded import.
- **No `shell=True`, no shell string.** Build a subprocess command as a list.
- **Hooks are exec form: one executable in `command`, its arguments in `args`.** Claude Code then
  spawns it directly, with no shell, so `&&`, `|`, `$( )` and the rest are not merely discouraged
  but inert. Name scripts as `${CLAUDE_PROJECT_DIR}`-relative paths, which exec form substitutes
  as plain strings, so a hook still finds its script after the agent has run `cd`.
  *Why: a hook that needs `sh` fails where `sh` is absent, and it fails **open** — the check
  silently stops running while still looking healthy. Logic beyond one command belongs in a
  script under `tools/`, which is also then testable.*
- **Never assert on a literal path separator in a test.** Compare against `str(Path(...))`.

## What is mechanically enforced

Everything above is checked. This table says by what, so you know which rules bite immediately and
which rest on your own discipline.

| Rule | Enforced by |
|---|---|
| No `def` inside a function, unless it is returned | `tools/check_conventions.py` `nested-def` |
| No `class` inside a function | `tools/check_conventions.py` `nested-class` |
| No comprehension with two `for`s, or inside another | `tools/check_conventions.py` `complex-comprehension` |
| Guard clauses; ≤3 nested blocks | `PLR1702` |
| ≤40 statements, complexity ≤8, ≤12 locals, ≤5 args | `PLR0915` `C901` `PLR0914` `PLR0913` |
| No `print`, `__main__` blocks included (`tools/` exempt) | `T20` |
| Correct logging calls | `LOG` `G` — **stdlib only**; neither sees `loguru` call sites |
| Never swallow exceptions; `raise ... from e` | `BLE` `B904` `TRY` |
| Never `raise ... from None` | `tools/check_conventions.py` `raise-from-none` — `B904` accepts it |
| No `getattr`/`setattr`/`delattr` with a computed name | `tools/check_conventions.py` `dynamic-attribute` |
| A module defining `main` has an `if __name__ == "__main__":` block | `tools/check_conventions.py` `missing-main-guard` |
| An exit from an `except` reports what it caught | `tools/check_conventions.py` `silent-exit` |
| An HTTP client comes from `build_client`, never a bare `httpx.Client()` | `tools/check_conventions.py` `raw-httpx-client` |
| Tests replace the network with `httpx.MockTransport`, never by patching httpx | `tools/check_conventions.py` `patched-httpx` |
| typer parameters use `Annotated`, never `= typer.Option(...)` | `tools/check_conventions.py` `typer-default` |
| Full annotations on public signatures | `ANN` + `ty` |
| Docstrings on public functions/classes | `D101` `D102` `D103` |
| No lambda assigned to a name | `E731` |
| Timezone-aware datetimes | `DTZ` |
| A deprecation warning fails the test that triggers it | pytest `filterwarnings = ["error"]` |
| No unused args, no private-member access | `ARG` `SLF` |
| `pathlib` over `os.path` | `PTH` |
| Explicit `encoding=` on reads and writes | `unspecified-encoding` |
| No `shell=True`, no shell string | `S602` `S604` `S605` |
| Hooks are exec form: `command` plus `args`, no shell | *convention — review only* |
| No literal path separators asserted in tests | *convention — review only* |
| No edits to repo files while on `main` | `tools/branch_guard.py` via `PreToolUse` |
| No turn ends with a changed file failing the gate, or a failing test | `tools/stop_gate.py` via `Stop` — blocks once, then lets you stop and explain |
| No direct commits to `main` (merges allowed) | `no-commit-to-branch` at `pre-commit` stage only |
| Conventional Commit format, every branch | `conventional-pre-commit` (prek, `commit-msg` stage) |
| Branch consolidated to one commit before merge | `tools/finish_branch.py`, when the branch is finished with it |
| `main` receives merge commits, never fast-forwards | `tools/finish_branch.py`, when the branch is finished with it |
| Merge subject describes the work, never `Merge branch '...'` | `tools/finish_branch.py`, when the branch is finished with it — by hand, review only: `Merge` is exempt from the message check |
| Clean tree before starting work | *convention — `SessionStart` reports it, does not block* |
| `prek` installed and all three git shims present | `tools/session_doctor.py` via `SessionStart` — reports, does not block |
| Commit summary ≤72 chars, imperative | *convention — review only* |
| One logical change per commit | *convention — review only* |
| Name intermediates | *convention — review only* |
| Dataclass over ad-hoc dict | *convention — review only* |
| Inject clock/rng/client | *convention — review only* |
| No metaclass tricks or runtime-generated attributes | *convention — review only* |
| `if __name__ == "__main__":` on other runnable modules | *convention — review only* |

The convention rows are checked by `/code-review`, not by a linter. They matter just as much.

## Escape hatch

Each `check_conventions.py` rule has an id, and a line opts out of one with `# noqa: <id>` —
`# noqa: nested-def` on the `def` line of a closure that genuinely cannot be returned, say. Name
several ids with commas. Use it rarely and say why in a comment beside it.

## Git

- **Never edit on `main`.** Check `git status --short --branch` first. On `main`, branch before the
  first edit: `git switch -c <type>/<short-name>`, e.g. `feat/fetch-retry`. A dirty tree you did
  not make: resolve it or ask before starting.
- **Conventional Commits:** `type(scope): summary` — imperative, lower case, no period, at most 72
  characters; the body says why. Types: `feat` `fix` `docs` `refactor` `test` `chore` `build` `ci`
  `perf` `style` `revert`. One logical change per commit: if the summary needs "and", split it.
- **Finish a branch with the script, never by hand:**
  `uv run python tools/finish_branch.py "feat(x): summary"`. It squashes, gates, tests, and merges
  into `main` with `--no-ff`; `--keep-commits` keeps several commits when the branch holds several
  changes.
- Checkpointing broken work, a conflict with `main`, the merge message, and the reasons for all of
  it: the **git-workflow** skill.

## Commands

```bash
prek run --files <path> [<path> ...]    # the whole gate, on the files you touched
prek run ty --all-files                 # one hook by id: ruff-check, ty, rumdl, conventions
prek run --all-files                    # the whole gate, every tracked file
uv run pytest                           # tests, which the gate does not run
```

Run the linters **through prek, never directly.** `ty` is not installed outside the gate, so
`ty check` is "command not found", and a `ruff` on PATH can be a different version from the hook's
pin and disagree with it. prek runs the pinned versions, so what passes here passes at commit.

First-time setup needs **all three** shims. `prek install` alone wires only `pre-commit`, which
silently disables the commit-message check *and* makes `git merge --no-ff` into `main` fail:

```bash
prek install -t pre-commit -t commit-msg -t pre-merge-commit
```

Add dependencies with `uv add` / `uv add --dev`, never by editing `pyproject.toml` by hand.
Install or upgrade tools with `uv tool install` / `uv tool upgrade`.
