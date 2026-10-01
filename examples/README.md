# Demonstration specs

Feature specs to build **inside a generated project**, as a way of exercising the template. They
are not shipped: everything that becomes a generated project lives under `template/`, and this
directory sits beside it.

Each spec describes a command — its flags, the service it calls, what it prints and how it fails —
plus the tests that would prove it. None of them says how to structure the code. That is the point:
the generated project's `CLAUDE.md`, its gate and its `python-cli-modern` skill are supposed to
supply the structure, and a spec handed to an agent is how to find out whether they do.

## Running one

1. Generate a `cli-modern` project, or update the dogfood to the current template.
2. Start a Claude Code session **rooted in that project**, so its hooks and skills load.
3. Hand the agent the spec, unedited. Watch rather than steer.
4. Record what the template did and did not catch in [TODO.md](../TODO.md).

Things worth watching for: the branch guard on the first edit, whether the gate's stderr was
actionable, whether the skill was loaded at all, and whether the result needed `CLAUDE.md` rules
that nothing enforces.

## The specs

| Spec | Exercises |
|---|---|
| [geo.md](geo.md) | an `httpx` client injected for tests, a response model with aliases, a required User-Agent |
| [currency.md](currency.md) | exact `Decimal` arithmetic end to end, input parsing as a usage error, a pure core |

Both were once shipped in the scaffold, and the original implementations survive in history at
[`d8e26b0`](https://github.com/GrndZero101/python-template/tree/d8e26b0/template/src) — useful for
comparing against what an agent builds from the spec, not for copying.
