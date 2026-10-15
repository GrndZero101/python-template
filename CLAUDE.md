# Working on this template repository

This repo is the **base** of a [copier](https://copier.readthedocs.io/) template in two layers,
applied to the same project. The root is **not** a Python project.

- **The base** is the root `copier.yml` plus `template/`: the hooks, `tools/`, `CLAUDE.md`, the
  shared skills and a fallback `pyproject.toml`. It also stands alone, for a prototype or a repo
  adopting the guards.
- **A use case** is a template of its own, in a repository of its own, with its own `copier.yml` and
  `template/`. [python-template-cli-typer](https://github.com/GrndZero101/python-template-cli-typer)
  is the typer CLI. Its one task applies the base to the same directory, so one `copier copy`
  yields both layers, each with its own answers file.

@template/CLAUDE.md

The rules imported above govern every file under `template/` — that is the code being shipped, and
it is held to exactly the standard it preaches. A use case's repository holds its own code to the
same rules. What follows is only what differs at this level.

## Layout

| Path | What it is |
|---|---|
| `template/` | The base layer of a generated project. Holds Jinja; not runnable in place. |
| `copier.yml` | The base's questions, exclusions and bootstrap tasks. |
| `tests/test_template.py` | Generates the base alone and runs its gate. CI adds the CLI repo's suite. |
| `.pre-commit-config.yaml` | Governs **this** repo. `.git` is here, so this is what the git hooks read. |
| `pyproject.toml` | Dev deps and lint config for the root. Not published, not importable. |
| `TODO.md` | Outstanding work on the template itself. Not shipped. |

**Every generated file has exactly one owner**: it is rendered by the base or by a use case, never
both. Two templates rendering the same path conflict on `copier update` (markers in the file), so
the split is by directory and a test in the CLI repo's suite checks it. The base owns `CLAUDE.md`,
`tools/` and its tests, `.claude/settings.json`, `.pre-commit-config.yaml`, `.gitignore`,
`.python-version`, `LICENSE`, `.debugmcp.json`, `.vscode/`, `ruff-base.toml`, the skills
`git-workflow`, `python-debug` and `python-cli`, and `.copier-answers.base.yml`. The one exception
is `pyproject.toml`, which the use case owns: the base also renders a minimal one under
`_skip_if_exists`, which copier never overwrites, so it reaches only a project that has none. The
use case owns `pyproject.toml`, `README.md`, `src/`, `tests/`, `.copier-answers.yml`,
`.claude/rules/cli-typer.md` and the skills `python-cli-typer`, `python-data` and `python-tui`.

A file under a `template/` — this one, or a use case's — carries a `.jinja` suffix only when it
must name something the answers decide:

- the project files `pyproject.toml`, `README.md`, `LICENSE`, `.pre-commit-config.yaml`,
  `.copier-answers.yml`, `.copier-answers.base.yml` and `.python-version`;
- in a use case, the source and test modules that name the script or import the package, which the
  CLI repo's `CLAUDE.md` lists.

Everything else — `CLAUDE.md`, all of `tools/`, every other skill file — ships literally.

## The two gates

`.git` sits at the root, so `prek install` wires the git hooks to the **root** config. That config
owns the commit-level rules — the message check and `no-commit-to-branch` — lints the repo's own
markdown, and lints the one Python module the root holds.

**`template/` is not checked in place, and cannot be.** It contains Jinja and has no
`pyproject.toml` — only `pyproject.toml.jinja` — so `ruff` would fall back to default rules and `ty`
would find no environment. Its `.pre-commit-config.yaml` is suffixed `.jinja` for the same reason:
that keeps prek from picking the directory up as a workspace member and running a gate there that
is guaranteed to fail.

What covers it instead is `tests/test_template.py`. It generates the base **alone** and runs
**that project's** gate and test suite inside it. This is the stronger check of the two — it
verifies the thing that actually ships rather than the thing it is made from — and it costs about
fifteen seconds. It runs at commit, and only when the commit touches something that can change a
generated project: `template/`, `tests/`, `copier.yml`, `pyproject.toml` or `uv.lock`. A commit of
`TODO.md` alone skips it. To skip it deliberately anyway:

```bash
SKIP=generation-tests git commit -m "..."
```

Copier includes uncommitted working-tree changes when the template is a local path (it warns
`DirtyLocalWarning`), so the tests validate what you are about to commit, not the last commit.

**The base layered under a use case is not checked locally.** That is the CLI repo's suite, which
generates through the CLI template and runs the full gate, the hooks' tests and the update tests.
Run it against an unpushed base change with `BASE_TEMPLATE_DIR=$PWD uv run pytest` in a clone of
python-template-cli-typer. Most of what the base ships — the hooks, the gate, `finish_branch.py`, the
licence — is exercised only that way.

On a push that touches what `generation-tests` watches, the root gate's config or the workflow,
`.github/workflows/ci.yml` runs the root gate on Linux, then on Linux and macOS this repo's suite
and the CLI repo's, checked out into `cli/` with this checkout as the base — the only automatic
check of the layering. A docs-only push runs nothing. Push a branch to see macOS before merging.
On CI (`CI=true`) a test needing `uv`, `prek` or `copier` fails rather than skips when the tool is
missing; `prek` and `copier` come from the dev group.

Windows runs only when asked: `gh workflow run ci.yml --ref <branch> -f windows=true`. The targets
are Unix-alikes, and Windows took ten times Linux's time, so it is checked at milestones and in work
aimed at it, not on every push. That run is the only check of the portability rules away from a
Unix-alike, so they rest on review in between.

The edit-time `PostToolUse` gate uses `find_gate_root` in `template/tools/hook_payload.py`, which
walks up from the edited file to the nearest `.pre-commit-config.yaml`, bounded by the repo root.
Inside a generated project that lands on the root, which is the case it exists to serve. In *this*
repo every file resolves to the root config, and that config excludes `^template/` — so editing
something under it is not gated as you type. The root's hook passes
`--skip no-commit-to-branch,generation-tests` explicitly, so a save never pays for the generation
suite either; the generation test catches template edits at commit instead. Editing a root file the
config does not match, such as `TODO.md`, likewise leaves the gate standing down rather than
blocking.

The `Stop` hook is registered here the same way, with `--skip no-commit-to-branch,generation-tests`
and `--no-tests`: the root's test suite *is* the generation suite, which a stop should not pay for.
It still gates every changed root file before a turn ends, and, like the edit-time gate, it cannot
see into `template/`.

## Commands

Run from the repo root:

```bash
prek run --all-files            # the whole gate, generation test included (~15 s)
uv run pytest                   # the generation test only
copier copy --trust . /tmp/scratch    # the base alone, by hand, to poke at the result
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

It runs the root's whole gate before merging, generation test included: about fifteen seconds.
`--no-tests` because that test *is* this repo's suite, so running it again would double it.

## Sessions

Work is cut into sessions at checkpoints, which `TODO.md` defines under "Sessions and
checkpoints" and names in each phase. At one, finish and merge the step, update `TODO.md` so a
fresh session can start from it alone, then tell the user: "Checkpoint: start a new session", with
the next step. Don't carry on into the next step in the same session.
