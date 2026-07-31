# Working on this template repository

This repo is a [copier](https://copier.readthedocs.io/) template. The root is **not** a Python
project: everything that becomes a generated project lives under `template/`, which is what
`_subdirectory` in `copier.yml` points at.

@template/CLAUDE.md

The rules imported above govern every file under `template/` — that is the code being shipped, and
it is held to exactly the standard it preaches. What follows is only what differs at this level.

## Layout

| Path | What it is |
|---|---|
| `template/` | Becomes the generated project. Holds Jinja; not runnable in place. |
| `copier.yml` | The questions, the exclusions and the generation tasks. |
| `tests/test_template.py` | Generates a project per type and runs its gate. The only check on `template/`. |
| `.pre-commit-config.yaml` | Governs **this** repo. `.git` is here, so this is what the git hooks read. |
| `pyproject.toml` | Dev deps and lint config for the root. Not published, not importable. |
| `TODO.md` | Outstanding work on the template itself. Not shipped. |

Only five files under `template/` carry a `.jinja` suffix: `pyproject.toml`, `README.md`,
`.pre-commit-config.yaml`, `.copier-answers.yml` and the two example test modules. Everything else —
`CLAUDE.md`, all of `tools/`, every skill, and all six source modules — ships literally. The source
modules manage it because their internal imports are **relative**, so nothing inside `src/` names the
package and copier only has to render the directory name. Keep it that way: an absolute import there
would force another file to become a template.

## The two gates

`.git` sits at the root, so `prek install` wires the git hooks to the **root** config. That config
owns the commit-level rules — the message check and `no-commit-to-branch` — lints the repo's own
markdown, and lints the one Python module the root holds.

**`template/` is not checked in place, and cannot be.** It contains Jinja and has no
`pyproject.toml` — only `pyproject.toml.jinja` — so `ruff` would fall back to default rules and `ty`
would find no environment to resolve `httpx` or `typer` through. Its `.pre-commit-config.yaml` is
suffixed `.jinja` for the same reason: that keeps prek from picking the directory up as a workspace
member and running a gate there that is guaranteed to fail.

What covers it instead is `tests/test_template.py`. It generates a project for each of the five
project types and runs **that project's** gate and test suite inside it. This is the stronger check
of the two — it verifies the thing that actually ships rather than the thing it is made from — but
it costs about a minute, which is why the gate is slow. To skip it deliberately:

```bash
SKIP=generation-tests git commit -m "docs: ..."
```

Copier includes uncommitted working-tree changes when the template is a local path (it warns
`DirtyLocalWarning`), so the tests validate what you are about to commit, not the last commit.

The edit-time `PostToolUse` gate uses `find_gate_root` in `template/tools/hook_payload.py`, which
walks up from the edited file to the nearest `.pre-commit-config.yaml`, bounded by the repo root.
Inside a generated project that lands on the root, which is the case it exists to serve. In *this*
repo every file resolves to the root config, and that config excludes `^template/` — so editing
something under `template/` is not gated as you type. The generation tests catch it at commit
instead. Editing a root file the config does not match, such as `TODO.md`, likewise leaves the gate
standing down rather than blocking.

## Commands

Run from the repo root:

```bash
prek run --all-files            # the whole gate, generation tests included (~1 min)
uv run pytest                   # generation tests only
uv run pytest -k cli-modern     # one project type, when iterating
copier copy --trust . /tmp/scratch    # generate by hand to poke at the result
```

`template/` has no venv and nothing to run — `uv run --directory template` no longer works, because
there is no `pyproject.toml` there to run against.

**Never `cd template`.** Use `uv run --directory template`. Claude Code's hooks inherit the shell's
working directory, and a leftover `cd` makes them resolve `template/template/tools/...` and fail.

## Branching

Identical to the imported rules: never edit on `main`, branch first, `main` receives only merge
commits. The `PreToolUse` guard runs from the root and covers the whole repo, `template/` included.
