# Python rules

Enforced by a PostToolUse hook that auto-formats, then blocks on anything left. Violations block
the edit — fix them, don't work around them.

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
  for module-level mutable state.
  *Why: a function must be re-runnable in isolation from a breakpoint, with values you choose.*
- Never swallow an exception. `raise ... from e`, or `logger.exception(...)`.
  *Why: a bare `except: pass` destroys the traceback that tells you where it started.*
- A configured logger writing to **stderr**, never `print`, outside a `__main__` block. Stdlib
  `logging` by default; `loguru` where a stack skill says so.
  *Why: stdout is reserved for a command's data, so it stays pipeable. Diagnostics that land there
  corrupt the output a caller is parsing.*
- Every module that can run standalone gets `if __name__ == "__main__":`.

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
- **Hook commands are a single executable invocation, never a shell pipeline.** No `&&`, `||`,
  `|`, `;`, `{ }`, `1>&2`, `if`/`fi`, or `$( )`.
  *Why: a hook that needs `sh` fails where `sh` is absent, and it fails **open** — the check
  silently stops running while still looking healthy. Logic beyond one command belongs in a
  script under `tools/`, which is also then testable.*
- **Never assert on a literal path separator in a test.** Compare against `str(Path(...))`.

## What is mechanically enforced

Everything above is checked. This table says by what, so you know which rules bite immediately and
which rest on your own discipline.

| Rule | Enforced by |
|---|---|
| No `def` inside a function | `tools/check_nested_defs.py` |
| Guard clauses; ≤3 nested blocks | `PLR1702` |
| ≤40 statements, complexity ≤8, ≤12 locals, ≤5 args | `PLR0915` `C901` `PLR0914` `PLR0913` |
| No `print` outside `__main__` | `T20` |
| Correct logging calls | `LOG` `G` — **stdlib only**; neither sees `loguru` call sites |
| Never swallow exceptions; `raise ... from e` | `BLE` `B904` `TRY` |
| Full annotations on public signatures | `ANN` + `ty` |
| Docstrings on public functions/classes | `D101` `D102` `D103` |
| No lambda assigned to a name | `E731` |
| Timezone-aware datetimes | `DTZ` |
| No unused args, no private-member access | `ARG` `SLF` |
| `pathlib` over `os.path` | `PTH` |
| Explicit `encoding=` on reads and writes | `unspecified-encoding` |
| Hook commands are one executable, not a shell pipeline | *convention — review only* |
| No literal path separators asserted in tests | *convention — review only* |
| No edits to repo files while on `main` | `tools/branch_guard.py` via `PreToolUse` |
| No direct commits to `main` (merges allowed) | `no-commit-to-branch` at `pre-commit` stage only |
| Conventional Commit format, every branch | `conventional-pre-commit` (prek, `commit-msg` stage) |
| Branch consolidated to one commit before merge | *convention — review only* |
| `main` receives merge commits, never fast-forwards | *convention — review only* |
| Clean tree before starting work | *convention — `SessionStart` reports it, does not block* |
| Commit summary ≤72 chars, imperative | *convention — review only* |
| One logical change per commit | *convention — review only* |
| No `class` inside a function | *convention — review only* |
| Name intermediates; no multi-`for` comprehensions | *convention — review only* |
| Dataclass over ad-hoc dict | *convention — review only* |
| Inject clock/rng/client | *convention — review only* |
| No `getattr` dispatch or metaclass tricks | *convention — review only* |
| `if __name__ == "__main__":` on runnable modules | *convention — review only* |

The convention rows are checked by `/code-review`, not by a linter. They matter just as much.

## Escape hatch

A genuinely necessary closure that is not returned can carry `# noqa: nested-def` on its `def`
line. Use it rarely and say why in a comment.

## Branching

**Never edit on `main`.** Before starting any work, check the branch and the tree:

```bash
git status --short --branch
```

- If the tree is dirty, resolve it first — commit it, stash it, or ask. Never start new work on top
  of someone else's uncommitted changes, because the next commit cannot then be split cleanly.
- If on `main`, branch before the first edit: `git switch -c <type>/<short-name>`, using the same
  types as the commit list below (`feat/publicip-retry`, `fix/hook-stderr`, `chore/bump-ruff`).

This is enforced twice, deliberately, because the two catch different mistakes:

| Guard | Fires when | Effect |
|---|---|---|
| `PreToolUse` branch guard | `Edit`/`Write` to a file **inside the repo** while on `main` | blocks the edit before it lands |
| `no-commit-to-branch` | `git commit` on `main` | blocks the commit |

The edit-time guard is the one that matters. Without it, work lands in `main`'s working tree and only
gets caught at commit, when the fix is a `stash`/`branch`/`pop` dance rather than one command.

*Why: `main` should always be a state you can return to. A dirty `main` working tree means you
cannot check out anything else without carrying changes along, and you lose the ability to tell what
was already good from what you are in the middle of.*

**Override**, for a genuine one-line emergency: `touch .allow-main-edit` (gitignored). It disables
only the edit guard; the commit guard still needs `git commit --no-verify`, which also skips every
other check. Prefer branching — it costs one command.

## Merging

`main` only ever receives **merge commits** — never a direct commit, never a fast-forward. The merge
commit is what records that a branch existed and what it was for, so `git log --first-parent main`
reads as one entry per piece of work while `git log` still has the detail for `bisect`.

Consolidate the branch to a single commit *before* merging. Two paths; prefer the first.

### Squash into a clean branch (default)

```bash
git switch -c feat/x-wip                  # scratch: commit as often as you like
# ...work...
git switch main
git switch -c feat/x                      # clean branch cut from current main
git merge --squash feat/x-wip
git commit -m "feat(x): ..."              # full gate + message check run HERE
git rebase main                           # resolve conflicts HERE, never on main
git switch main
git merge --no-ff feat/x
git branch -D feat/x feat/x-wip
```

Nothing is rewritten anywhere: `feat/x-wip` sits untouched until you delete it, so a botched
consolidation costs nothing. And because the consolidation is an ordinary commit on a branch, the
commit that reaches `main` is exactly the one the full gate inspected.

### Rebase in place (only when the branch holds more than one change)

Squashing forces everything into one commit, which produces exactly the "and" commit the rule below
forbids when a branch genuinely did two things. Consolidate with autosquash instead:

```bash
git commit --fixup=HEAD                             # corrections, as you go
GIT_SEQUENCE_EDITOR=true git rebase --autosquash main
prek run --all-files                                # REQUIRED — see below
git switch main && git merge --no-ff feat/x
```

**No hooks run during a rebase** — not the gate, not the message check. A rebase that resolved a
conflict produces a tree nothing has ever checked, so `prek run --all-files` afterwards is not
optional. For the same reason, never consolidate with an interactive-rebase squash and assume the
result was verified. It was not.

### Never resolve conflicts on `main`

Bring `main` into the branch and resolve there, so the merge into `main` is always clean. This is not
just hygiene: git runs `pre-commit` rather than `pre-merge-commit` when you commit a *resolved*
merge, so `no-commit-to-branch` blocks you mid-merge and leaves it half-applied. The `PreToolUse`
guard stops you editing the conflicted file on `main` in the first place.

### Checkpointing broken work

Scratch commits still use Conventional Commit form — `chore(x): wip` costs nothing and keeps the
history readable while it exists. But half-written code will not pass `ty`, so skip the *code* gate
without skipping the *message* check:

```bash
SKIP=ruff-format,ruff-check,ty,rumdl-fmt,rumdl,no-nested-defs git commit -m "chore(x): wip"
```

`git commit --no-verify` is the wrong tool here — it skips the message check too. Worth an alias:

```bash
git config alias.wip '!SKIP=ruff-format,ruff-check,ty,rumdl-fmt,rumdl,no-nested-defs git commit'
```

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`.

- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`.
- Summary in the imperative, lower case, no trailing period, ≤72 characters.
- Scope is optional and is a module or area, e.g. `feat(cli): add --json output`.
- Breaking changes get a `!` before the colon *and* a `BREAKING CHANGE:` footer.
- Body explains **why**, not what — the diff already says what.
- One logical change per commit. If the summary needs "and", split it.

*Why: the type prefix is what makes history greppable and changelogs derivable, and it forces
the "is this one change?" question at the point where it is cheap to fix.*

## Commands

```bash
ruff format . && ruff check --fix .              # format, then auto-fix
ty check                                         # types
rumdl fmt . && rumdl check .                     # markdown
uv run pytest                                    # tests
uv run python tools/check_nested_defs.py src tests tools
prek run --all-files                             # everything above, as one gate
```

First-time setup needs **all three** shims. `prek install` alone wires only `pre-commit`, which
silently disables the commit-message check *and* makes `git merge --no-ff` into `main` fail:

```bash
prek install && prek install -t commit-msg && prek install -t pre-merge-commit
```

Add dependencies with `uv add` / `uv add --dev`, never by editing `pyproject.toml` by hand.
Install or upgrade tools with `uv tool install` / `uv tool upgrade`.
