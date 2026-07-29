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
- `logging`, never `print`, outside a `__main__` block.
- Every module that can run standalone gets `if __name__ == "__main__":`.

## Agent-friendliness

- Explicit over dynamic. No `getattr` dispatch, no metaclass tricks, no runtime-generated
  attributes.
  *Why: these defeat grep and breakpoints alike — the two ways code gets navigated.*
- Full type annotations on every public signature.
- Errors name the fix: `raise ValueError(f"expected .json, got {path.suffix}; pass a JSON file")`.
- Tests are deterministic: seed randomness, freeze time, no network.

## What is mechanically enforced

Everything above is checked. This table says by what, so you know which rules bite immediately and
which rest on your own discipline.

| Rule | Enforced by |
|---|---|
| No `def` inside a function | `tools/check_nested_defs.py` |
| Guard clauses; ≤3 nested blocks | `PLR1702` |
| ≤40 statements, complexity ≤8, ≤12 locals, ≤5 args | `PLR0915` `C901` `PLR0914` `PLR0913` |
| No `print` outside `__main__` | `T20` |
| Never swallow exceptions; `raise ... from e` | `BLE` `B904` `TRY` |
| Full annotations on public signatures | `ANN` + `ty` |
| Docstrings on public functions/classes | `D101` `D102` `D103` |
| No lambda assigned to a name | `E731` |
| Timezone-aware datetimes | `DTZ` |
| No unused args, no private-member access | `ARG` `SLF` |
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

Add dependencies with `uv add` / `uv add --dev`, never by editing `pyproject.toml` by hand.
Install or upgrade tools with `uv tool install` / `uv tool upgrade`.
