# python-template

A [copier](https://copier.readthedocs.io/) template for Python projects built around one idea:
every rule in the generated `CLAUDE.md` exists so a human (or an AI agent) can stop the program and
inspect it. Structure, debuggability and portability rules are mechanically enforced by lint config
and a `prek` gate — not just documented and hoped for.

Generated projects get: the rule set, a `PreToolUse` guard that refuses edits to `main`, a
`PostToolUse` gate that lints on every save, `ruff`/`ty`/`rumdl`/`prek` configured, a custom check
for `def` inside `def`, and the Claude Code skills matching the stack you pick.

## Prerequisites

```bash
uv tool install copier
uv tool install prek
```

`uv` itself: see [the uv docs](https://docs.astral.sh/uv/getting-started/installation/).

---

## Path A — start a new project from this template

```bash
copier copy gh:GrndZero101/python-template my-project     # answer the prompts
cd my-project
```

That is the whole setup. Generation already ran `git init -b main`, `uv sync`, the initial commit,
and all three `prek` shims. Verify and start work:

```bash
prek run --all-files --skip no-commit-to-branch   # should be all green
uv run pytest
git switch -c feat/first-thing                    # never work on main
```

You will be asked for: project name, package name, description, author name and email, minimum
Python version, and **project type** — one of `cli-modern`, `cli-stdlib`, `fastapi`, `tui`, `data`.
The type selects dependencies, lint rules and which skill ships. Only `cli-modern` includes the
example CLI; the others get the infrastructure and a bare package.

### Keeping it in sync with the template

```bash
git status --short            # must be clean; copier refuses otherwise
copier update --trust
git diff                      # review — nothing is committed for you
prek run --all-files --skip no-commit-to-branch
git switch -c chore/template-update
git commit -am "chore: pull template updates"
```

`--trust` is required because the template runs tasks. Updates are a three-way merge: files you
have edited keep your changes, and genuine conflicts arrive as markers to resolve by hand.

To pin a version, or to move deliberately:

```bash
copier copy --vcs-ref v1.2.0 gh:GrndZero101/python-template my-project
copier update --trust --vcs-ref v1.3.0
```

Do not delete `.copier-answers.yml` — `copier update` reads it to know what you answered.

---

## Path B — work on the template itself

```bash
git clone https://github.com/GrndZero101/python-template
cd python-template
uv sync
prek install && prek install -t commit-msg && prek install -t pre-merge-commit
```

All three shims are required. `prek install` alone wires only `pre-commit`, which silently skips
the commit-message check and breaks `--no-ff` merges into `main`.

```bash
git switch -c feat/whatever    # never edit on main; a hook enforces it
```

Edit under `template/`, then:

```bash
uv run pytest                   # generate a project per type, run its gate and suite (~1 min)
uv run pytest -k cli-modern     # one type, while iterating
prek run --all-files            # the whole gate, generation tests included
```

To look at real output rather than an assertion:

```bash
copier copy --trust --defaults -d project_name=Scratch -d package_name=scratch .  /tmp/scratch
```

**`template/` cannot be linted or run where it sits** — it holds Jinja and has no `pyproject.toml`.
The generation tests are the only thing that verifies it, which is why they are wired into the gate.
See [CLAUDE.md](CLAUDE.md) for why, and for the branching and merge rules.

## Layout

- **`template/`** — everything a generated project receives.
- **`copier.yml`** — questions, exclusions, generation tasks.
- **`tests/test_template.py`** — generates projects and runs their gates. The only check on
  `template/`.
- **`.pre-commit-config.yaml`** — the gate for this repository.
- **`TODO.md`** — outstanding work.

## License

[MIT](LICENSE)
