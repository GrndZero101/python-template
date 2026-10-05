# Demonstration specs

Feature specs to build **inside a generated project**, as a way of exercising the template. They
are not shipped: everything that becomes a generated project lives under `template/`, and this
directory sits beside it.

Each spec describes a command — its flags, its input or the service it calls, what it prints and
how it fails — plus the tests that would prove it. None of them says how to structure the code.
That is the point: the generated project's `CLAUDE.md`, its gate and its skills —
`python-cli-modern`, and `python-data` or `python-tui` where the spec calls for them — are
supposed to supply the structure, and a spec handed to an agent is how to find out whether they do.

## Running one

Each run is one spec built by one model in a fresh project, then judged in a second session by a
stronger model. `sonnet` is the baseline: the claim being tested is that a mid-tier model builds a
good tool cheaply when the template carries the knowledge. A `haiku` run now and then shows how far
below that the template still reaches; act on what it finds only when the fix would help any model.

The commands set `REPO` to this checkout and name the run after the spec and the model:

```bash
REPO=~/projects/github/GrndZero101/python-template
SPEC=geo MODEL=sonnet                 # or currency, spend, logs; or haiku, for a stretch run
RUN=~/scratch/spec-runs/$SPEC-$MODEL
```

### 1. Generate a fresh project

```bash
copier copy --trust --defaults --vcs-ref main \
  -d project_name="Spec Run" -d author_name="A Dev" -d author_email=dev@example.com \
  gh:GrndZero101/python-template "$RUN"
grep _commit "$RUN/.copier-answers.yml"   # note it: the template commit this run measures
```

It is generated on `main`, with prek's three git shims installed. Leave it on `main`: whether
the agent branches by itself is part of what is being observed.

### 2. Build: hand the agent the spec

```bash
cd "$RUN"
unset VIRTUAL_ENV    # one left over from another project makes uv warn in every tool result
claude --model "$MODEL" --permission-mode acceptEdits "$(cat "$REPO/examples/$SPEC.md")"
```

The spec goes in unedited, as the whole prompt. Approve the permission prompts that remain, but
**do not steer**: no hints, no corrections. A question the agent asks is a finding, so answer it
in as few words as the spec would allow. When it says it is finished, run `/cost`, note the
figure, and exit.

Your own `~/.claude` setup (global rules, MCP servers, memory) also loads in this session. Bear
that in mind when the agent does something the template does not teach.

### 3. Check it yourself

Still in `$RUN`:

```bash
SKIP=no-commit-to-branch prek run --all-files    # that hook always fails on main, by design
uv run pytest
```

Note pass or fail for each. The agent saying it is done is not evidence.

### 4. Review: a second session, a stronger model

```bash
claude --model opus --permission-mode plan \
  "$(cat "$REPO/examples/evaluate.md") Spec: $REPO/examples/$SPEC.md"
```

Plan mode keeps it read-only. [evaluate.md](evaluate.md) tells it what to read — the spec, the
diff, `.gate.log` and the build session's transcript — and to separate what the *template* should
change from what was just the model.

### 5. Record

Add a row to the results table under "Spec runs" in [TODO.md](../TODO.md), and turn each template
finding into an item in the phase it belongs to.

Things worth watching for while it builds: the branch guard on the first edit, whether the gate's
stderr was actionable, whether the skill was loaded at all, and whether the result needed
`CLAUDE.md` rules that nothing enforces.

## The specs

| Spec | Exercises |
|---|---|
| [geo.md](geo.md) | an `httpx` client injected for tests, a response model with aliases, a required User-Agent |
| [currency.md](currency.md) | exact `Decimal` arithmetic end to end, input parsing as a usage error, a pure core |
| [spend.md](spend.md) | `python-data`: a declared schema over CSV and parquet, a filtered and grouped pipeline, integer money, an empty result that keeps its types |
| [logs.md](logs.md) | `python-tui`: logic outside the app, validation before the screen opens, key bindings, a picker whose choice goes to stdout, Pilot tests |

`geo` and `currency` were once shipped in the scaffold, and the original implementations survive
in history at [`d8e26b0`](https://github.com/GrndZero101/python-template/tree/d8e26b0/template/src)
— useful for comparing against what an agent builds from the spec, not for copying.
