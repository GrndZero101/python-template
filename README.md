# python-template

A [copier](https://copier.readthedocs.io/) template for Python projects built around one idea:
every rule in the generated `CLAUDE.md` exists so a human (or an AI agent) can stop the program and
inspect it. Structure, debuggability and portability rules are mechanically enforced by lint config
and a `prek` gate — not just documented and hoped for.

Generated projects get: the rule set, a `PreToolUse` guard that refuses edits to `main`, a
`PostToolUse` gate that lints on every save, a `Stop` gate that re-checks every changed file and
runs the tests before a turn can end, `ruff`/`ty`/`rumdl`/`prek` configured, a custom checker
for the conventions no linter covers, and the Claude Code skills matching the stack you pick.

## Prerequisites

```bash
uv tool install copier
uv tool install prek
```

`uv` itself: see [the uv docs](https://docs.astral.sh/uv/getting-started/installation/).

---

## Path A — start a new project from this template

The template is two layers: the **base** (this repo: the hooks, the gate, `CLAUDE.md`, the shared
skills) and a **use case** layered on it.
[python-template-cli-typer](https://github.com/GrndZero101/python-template-cli-typer) is the typer
CLI, and copying it applies the base to the same directory:

```bash
copier copy --trust gh:GrndZero101/python-template-cli-typer my-project     # answer the prompts
cd my-project
```

The base also works alone, for a prototype or a repo adopting the guards:
`copier copy --trust gh:GrndZero101/python-template my-project`.

`--trust` is required because the template declares `_tasks` — the ones that run `git init`,
`uv sync` and install the shims. Without it copier exits 4 with "Template uses potentially unsafe
feature: tasks".

That is the whole setup. Generation already ran `git init -b main`, `uv sync`, the initial commit,
and all three `prek` shims. Verify and start work:

```bash
prek run --all-files --skip no-commit-to-branch   # should be all green
uv run pytest
git switch -c feat/first-thing                    # never work on main
```

You will be asked for: project name, package name, console script name, description, author name
and email, minimum Python version (3.12, 3.13 or 3.14), licence (MIT, Apache-2.0 or Proprietary)
and the name on its copyright line.

Every project is a CLI on typer, pydantic-settings, rich and loguru, with a scaffold: one
placeholder `about` command, with global and command flags that each resolve flag, then
environment variable, then config file, then default. A command that crunches data files or draws
a full-screen interface is added on top of it, following the `python-data` or `python-tui` skill,
rather than chosen at generation.

### Keeping it in sync with the template

A project records two sources, so an update is two commands, each on a clean tree and each touching
only its own layer's files: `copier update --trust` for the use case, and
`copier update --trust -a .copier-answers.base.yml` for the base. Run the second the same way as
the first.

```bash
git status --short                    # must be clean; copier refuses otherwise
git switch -c chore/template-update   # branch first; main takes no direct commits
copier update --trust                 # three-way merge into the working tree
# resolve conflicts, if any (below)
uv sync                               # before any check; see below
git diff                              # review; nothing is committed for you
prek run --all-files
uv run pytest
git add -A                            # -A, not -a: the template may have added files
git commit -m "chore(template): update to python-template-cli-typer <commit>"
git switch main
git merge --no-ff -m "chore(template): update to python-template-cli-typer <commit>" chore/template-update
git branch -d chore/template-update
```

`<commit>` is the `_commit` value copier just wrote to `.copier-answers.yml`.

**Run `copier update` yourself, not through an agent.** `--trust` is required because the template
declares `_tasks`. Every task is guarded to run on `copy` only, but copier asks for the flag anyway,
and it is the flag an agent's permission classifier refuses. Run it in a terminal of your own,
where copier can also prompt you; hand the agent the result to resolve and check.

**`uv sync` before any check.** A dependency the template dropped stays installed in `.venv` until
you sync. `ty` then still resolves an import that `pyproject.toml` no longer provides, and the gate
passes code that a fresh clone fails. `httpx` once did exactly that.

**New questions.** Interactively, `copier update` re-asks every question, using your recorded answer
as the default. Add `--skip-answered` (`-A`) to be asked only the ones you have not yet answered,
which means the questions the template has added since your last update. Under `--defaults`, a new
question silently takes the template's default, and that can be wrong. When `script_name` was
added, `--defaults` recorded the name derived from the package rather than the command the project
already had, and the update proposed renaming it in every file that carried it. For a
non-interactive update, answer new questions explicitly with
`--defaults --data script_name=my-cli`. Afterwards, `git diff .copier-answers.yml` shows any new
key, and each one is a question that was just answered for you.

**Conflicts.** Updates are a three-way merge: your edits survive wherever they don't overlap the
template's. Where they do, copier writes git-style inline markers: the project's version opens with
`<<<<<<< before updating`, and the new template render closes with `>>>>>>> after updating`. Copier
also records the file as unmerged, so `git status` lists it under *Unmerged paths* and the
usual tools work: `git checkout --ours <file>` keeps the project's version, `git checkout --theirs
<file>` takes the new template render, and `git add <file>` marks the file resolved. Taking a side
replaces the whole file, though, not just the conflicted hunks, so `--theirs` also drops any
project-only lines *outside* the markers. Use it only on a file you never meant to diverge;
otherwise resolve hunk by hunk.

While any file still holds markers, the edit-time gate pauses. A save lists the conflicted files
instead of reporting syntax errors from each one. `check-merge-conflict` blocks the commit if any
markers remain.

To pin a version, or to move deliberately, pass a commit. The template has no release tags yet;
once it does, `copier update` moves to the latest tag rather than the newest commit.

```bash
copier copy --trust --vcs-ref <commit> gh:GrndZero101/python-template-cli-typer my-project
copier update --trust --vcs-ref <commit>
```

Do not delete `.copier-answers.yml` — `copier update` reads it to know what you answered.

---

## Path B — work on the template itself

```bash
git clone https://github.com/GrndZero101/python-template
cd python-template
uv sync
prek install -t pre-commit -t commit-msg -t pre-merge-commit
```

All three shims are required. `prek install` alone wires only `pre-commit`, which silently skips
the commit-message check and breaks `--no-ff` merges into `main`.

```bash
git switch -c feat/whatever    # never edit on main; a hook enforces it
```

Edit under `template/`, then:

```bash
uv run pytest                   # generate the base alone, run its gate and suite
prek run --all-files            # the whole gate, generation test included
```

The base layered under a use case is checked by the use case's own suite. To run it against your
working tree, clone python-template-cli-typer beside this repo:

```bash
cd ../python-template-cli-typer
uv sync
BASE_TEMPLATE_DIR=../python-template uv run pytest
```

To look at real output rather than an assertion, generate through the CLI use case with the base
pointed at your tree:

```bash
copier copy --trust --defaults -d project_name=Scratch -d package_name=scratch \
  -d base_template="$PWD" ../python-template-cli-typer /tmp/scratch
```

**The template cannot be linted or run where it sits** — it holds Jinja and has no
`pyproject.toml`. The generation tests are the only thing that verifies it, which is why they are
wired into the gate.
See [CLAUDE.md](CLAUDE.md) for why, and for the branching and merge rules.

## Layout

- **`template/`** — the base layer: everything every generated project receives.
- **`copier.yml`** — the base's questions, exclusions and bootstrap tasks.
- **`tests/test_template.py`** — generates the base alone and runs its gate. The only local check
  on the template; CI also runs the CLI repo's suite against it.
- **`.pre-commit-config.yaml`** — the gate for this repository.
- **`TODO.md`** — outstanding work.

## License

[MIT](LICENSE)
