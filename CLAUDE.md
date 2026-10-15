# Working on this template repository

This repo holds [copier](https://copier.readthedocs.io/) templates in two layers, applied to the
same project. The root is **not** a Python project.

- **The base** is the root `copier.yml` plus `template/`: the hooks, `tools/`, `CLAUDE.md`, the
  shared skills and a fallback `pyproject.toml`. It also stands alone, for a prototype or a repo
  adopting the guards.
- **A use case** is a template of its own under `use-cases/<name>/`, with its own `copier.yml` and
  `template/`. `use-cases/cli-typer/` is the typer CLI. Its one task applies the base to the same
  directory, so one `copier copy` yields both layers, each with its own answers file.
- A use case moves to its own repository in phase 10 of `TODO.md`; this layout is how it lives here
  until then.

@template/CLAUDE.md

The rules imported above govern every file under `template/` and `use-cases/` — that is the code
being shipped, and it is held to exactly the standard it preaches. What follows is only what
differs at this level.

## Layout

| Path | What it is |
|---|---|
| `template/` | The base layer of a generated project. Holds Jinja; not runnable in place. |
| `copier.yml` | The base's questions, exclusions and bootstrap tasks. |
| `use-cases/cli-typer/` | The CLI layer: its own `copier.yml` and `template/`. Same caveats. |
| `tests/test_template.py` | Generates projects and runs their gate. The only check on the templates. |
| `.pre-commit-config.yaml` | Governs **this** repo. `.git` is here, so this is what the git hooks read. |
| `pyproject.toml` | Dev deps and lint config for the root. Not published, not importable. |
| `TODO.md` | Outstanding work on the template itself. Not shipped. |

**Every generated file has exactly one owner**: it is rendered by the base or by a use case, never
both. Two templates rendering the same path conflict on `copier update` (markers in the file), so
the split is by directory and a test checks it. The base owns `CLAUDE.md`, `tools/` and its tests,
`.claude/settings.json`, `.pre-commit-config.yaml`, `.gitignore`, `.python-version`, `LICENSE`,
`.debugmcp.json`, `.vscode/`, `ruff-base.toml`, the skills `git-workflow`, `python-debug` and
`python-cli`, and `.copier-answers.base.yml`. The one exception is `pyproject.toml`, which the use
case owns: the base also renders a minimal one under `_skip_if_exists`, which copier never
overwrites, so it reaches only a project that has none. The use case owns `pyproject.toml`,
`README.md`, `src/`, `tests/`, `.copier-answers.yml` and the skills `python-cli-typer`,
`python-data` and `python-tui`.

A file under either `template/` carries a `.jinja` suffix only when it must name something the
answers decide:

- the project files `pyproject.toml`, `README.md`, `.pre-commit-config.yaml`,
  `.copier-answers.yml`, `.copier-answers.base.yml` and `.python-version`;
- `cli.py` and `config.py`, which hold the script name and the environment-variable prefix;
- `conftest.py` and the test modules under `tests/`, which import the package by name;
- the reference tests in `.claude/skills/python-cli-typer/reference/`, for the same reason: they
  are copied into `tests/` unchanged, so they must already name the package.

Everything else — `CLAUDE.md`, all of `tools/`, every other skill file, and the other source modules
— ships literally. The source modules manage it because their internal imports are **relative**, so
nothing inside `src/` names the package and copier only has to render the directory name. Keep it
that way: an absolute import there would force another file to become a template. Anything that
needs the script name should import it from `config.py` rather than render it again.

## The two gates

`.git` sits at the root, so `prek install` wires the git hooks to the **root** config. That config
owns the commit-level rules — the message check and `no-commit-to-branch` — lints the repo's own
markdown, and lints the one Python module the root holds.

**`template/` and `use-cases/` are not checked in place, and cannot be.** They contain Jinja and
have no `pyproject.toml` — only `pyproject.toml.jinja` — so `ruff` would fall back to default rules
and `ty` would find no environment to resolve `httpx` or `typer` through. Their
`.pre-commit-config.yaml` is suffixed `.jinja` for the same reason: that keeps prek from picking the
directory up as a workspace member and running a gate there that is guaranteed to fail.

What covers them instead is `tests/test_template.py`. It generates projects — the CLI use case with
the base layered on, at the default Python and at the floor, and the base alone — and runs
**that project's** gate and test suite inside each. This is the stronger check of the two — it
verifies the thing that actually ships rather than the thing it is made from — but
it costs about a minute. It therefore runs only at commit, and only when the commit touches
something that can change a generated project: `template/`, `use-cases/`, `tests/`, `copier.yml`,
`pyproject.toml` or `uv.lock`. A commit of `TODO.md` alone skips it. To skip it deliberately anyway:

```bash
SKIP=generation-tests git commit -m "..."
```

Copier includes uncommitted working-tree changes when the template is a local path (it warns
`DirtyLocalWarning`), so the tests validate what you are about to commit, not the last commit.

On a push that touches what `generation-tests` watches, the root gate's config or the workflow,
`.github/workflows/ci.yml` runs the root gate on Linux and the generation suite on Linux, Windows
and macOS — the only check of the portability rules away from WSL. A docs-only push runs nothing.
Push a branch to see the other platforms before merging. On CI (`CI=true`) a test needing `uv`,
`prek` or `copier` fails rather than skips when the tool is missing; `prek` and `copier` come from
the dev group.

The edit-time `PostToolUse` gate uses `find_gate_root` in `template/tools/hook_payload.py`, which
walks up from the edited file to the nearest `.pre-commit-config.yaml`, bounded by the repo root.
Inside a generated project that lands on the root, which is the case it exists to serve. In *this*
repo every file resolves to the root config, and that config excludes `^(template|use-cases)/` —
so editing something under either is not gated as you type. The root's hook passes
`--skip no-commit-to-branch,generation-tests` explicitly, so a save never pays for the generation
suite either; the generation tests catch template edits at commit instead. Editing a root file the
config does not match, such as `TODO.md`, likewise leaves the gate standing down rather than
blocking.

The `Stop` hook is registered here the same way, with `--skip no-commit-to-branch,generation-tests`
and `--no-tests`: the root's test suite *is* the generation suite, a minute per stop. It still
gates every changed root file before a turn ends, and, like the edit-time gate, it cannot see into
`template/`.

## Commands

Run from the repo root:

```bash
prek run --all-files            # the whole gate, generation tests included (~1 min)
uv run pytest                   # generation tests only
uv run pytest -k gate           # only the generated project's gate, when iterating
copier copy --trust . /tmp/scratch    # generate by hand to poke at the result
```

`template/` has no venv and nothing to run — `uv run --directory template` no longer works, because
there is no `pyproject.toml` there to run against.

The hooks no longer care where the shell is. They are exec form, launched with
`--directory ${CLAUDE_PROJECT_DIR}`, so a `cd` into `template/` or another repo cannot make them
resolve the wrong script. Prefer `git -C <dir>` anyway: it keeps every command's context explicit.

## Branching

Identical to the imported rules: never edit on `main`, branch first, `main` receives only merge
commits. The `PreToolUse` guard runs from the root and covers the whole repo, `template/` included.

Finish a branch here with the template's own script, which runs unchanged from the root:

```bash
uv run python template/tools/finish_branch.py --no-tests "feat(x): summary"
```

It runs the root's whole gate before merging, generation suite included: about a minute.
`--no-tests` because that suite *is* this repo's tests, so running them again would double it.

## Sessions

Work is cut into sessions at checkpoints, which `TODO.md` defines under "Sessions and
checkpoints" and names in each phase. At one, finish and merge the step, update `TODO.md` so a
fresh session can start from it alone, then tell the user: "Checkpoint: start a new session", with
the next step. Don't carry on into the next step in the same session.
