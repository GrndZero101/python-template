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
| `template/` | Becomes the generated project. Ordinary, runnable, fully tested. |
| `.pre-commit-config.yaml` | Governs **this** repo. `.git` is here, so this is what the git hooks read. |
| `pyproject.toml` | `rumdl` settings for the repo's own markdown. No `[project]`, no venv. |
| `TODO.md` | Outstanding work on the template itself. Not shipped. |

## The two gates

`.git` sits at the root, so `prek install` wires the git hooks to the **root** config. That config
owns the commit-level rules — the message check and `no-commit-to-branch` — and lints the repo's own
markdown. It contains no code checks at all.

Code is covered because prek treats a nested `.pre-commit-config.yaml` as a **workspace member**: a
file under `template/` is routed to that config and run with `template/` as the working directory.
The lint list therefore exists once, in the file a generated project receives. A copy at this level
would have to duplicate the dependency list and build a second venv, because `ty` resolves imports
through the project environment.

Workspace discovery is a prek extension. Plain `pre-commit` does not have it and would leave
`template/` unchecked — the same trade already made for `repo: builtin`.

The edit-time `PostToolUse` gate resolves the same way from the other end — `find_gate_root` in
`template/tools/hook_payload.py` walks up from the edited file to the nearest `.pre-commit-config.yaml`,
bounded by the repo root. Inside a generated project that lands on the root and behaves exactly as a
hard-coded root would; here it lands on `template/`. Editing a root file that no config governs, such
as `TODO.md`, leaves the gate standing down rather than blocking.

## Commands

Run from the repo root:

```bash
prek run --all-files                    # root gate; delegates into template/
uv run --directory template pytest      # the generated project's test suite
uv run --directory template prek run --all-files    # that project's gate alone
```

**Never `cd template`.** Use `uv run --directory template`. Claude Code's hooks inherit the shell's
working directory, and a leftover `cd` makes them resolve `template/template/tools/...` and fail.

## Branching

Identical to the imported rules: never edit on `main`, branch first, `main` receives only merge
commits. The `PreToolUse` guard runs from the root and covers the whole repo, `template/` included.
