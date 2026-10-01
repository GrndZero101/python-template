---
name: python-debug
description: >-
  How to drive a live debugger from an agent with the standalone DebugMCP CLI — launching a script
  or a test file, conditional breakpoints and logpoints, reading values without drowning in debugpy's
  object trees, and the CLI's known gaps. Use when investigating a wrong value, an exception or a
  failing test at runtime, or whenever the alternative is adding print statements or guessing.
---

# Debugging with DebugMCP

Every rule in `CLAUDE.md` exists so a program can be stopped and inspected. This is how an agent
does the stopping. Inspect first, then edit: a breakpoint answers in one step what a temporary
`print` answers in three edits, and it leaves nothing to clean up.

## Setup, once per machine

The project ships `.debugmcp.json`; the server itself is installed per user, so a project never
forces Node onto anyone who does not want it. Node 20+ is required:

```bash
npm install --global debugmcp
claude mcp add --scope user debugmcp -- debugmcp serve --stdio
```

On native Windows, wrap the command: `claude mcp add --scope user debugmcp -- cmd /c debugmcp serve
--stdio`. Restart Claude Code afterwards.

Register it by hand like this rather than with `debugmcp configure`. That command also installs a
bundled `debug-live` skill written for the VS Code extension, whose advice on `testName` does not
apply to the CLI, and it replaces any existing `debugmcp` entry, including an extension one.

If the tools are absent from the session, the server is not registered. Say so; do not fall back to
print debugging silently.

## Two adapters, always named

`.debugmcp.json` registers two adapters that both claim `.py`, so `start_debugging` fails unless
`configurationName` picks one:

| `configurationName` | Runs | Use for |
|---|---|---|
| `python` | the requested file as a script | a module with an `if __name__ == "__main__":` block |
| `pytest` | `pytest <requested file>` through `tools/debug_pytest.py` | a test file |

Always pass `workingDirectory` as the **project root**. The CLI reads `.debugmcp.json` from that
directory and resolves `${workspaceFolder}` to it, so a subdirectory finds no adapters and a wrong
`program` path.

Both adapters launch through `uv run`, so the debuggee runs in the project's own `.venv` on every
platform without naming an OS-specific interpreter path.

## The loop

1. `add_breakpoint` on the earliest line that is still relevant. Lines are 1-based; re-check them
   after any edit, because they shift.
2. `start_debugging` with `fileFullPath`, `workingDirectory` and `configurationName`. It returns
   when the program pauses or finishes. "Ran to completion without stopping" means no breakpoint
   was hit: check the line, then the condition.
3. Inspect, step, and form a hypothesis. Trace a wrong value back to where it first went wrong;
   the first wrong value you see is usually a symptom.
4. `stop_debugging` and `clear_all_breakpoints` before moving on. Breakpoints outlive the session.

## Reading values

**Wrap anything that is not a scalar in `repr()`.** For a list, tuple, dict or model, both
`evaluate_expression` and `get_variables_values` return debugpy's object tree — kilobytes of dunder
methods, cut off before the actual elements:

```text
evaluate_expression  expression="settings"         # a 200-line tree of __class__, __dict__, ...
evaluate_expression  expression="repr(settings)"   # "Settings(verbose=True, output=<...>)"
```

Strings, numbers and booleans render directly. `list_variable_names` is cheap and shows what is in
scope; use it before asking for values.

## Narrowing to one test

`testName` does nothing under the CLI; it needs the VS Code extension's Test Explorer. The `pytest`
adapter runs the whole file. To stop in one case, use a **conditional breakpoint** keyed on that
case's values — in the test itself, or in the code under test. For example, in the `cli-modern`
scaffold:

```text
add_breakpoint   fileFullPath=<root>/tests/test_config.py  line=<n>  condition="raw == 'on'"
start_debugging  fileFullPath=<root>/tests/test_config.py  workingDirectory=<root>
                 configurationName=pytest
```

This also picks out a single parametrized case, which a test name could not.

## Output is not captured

The debuggee's stdout and stderr go nowhere the agent can read. There is no output tool. To watch
a value over time, use `add_logpoint` with `{expression}` interpolation — or pause and evaluate.
Never edit `print` into the code to see it.

## Status after continuing

Immediately after `continue_execution`, an instant status snapshot can still say "running" for a
program that has already exited. Call `get_debug_status` with `waitForPauseSeconds` for an answer
that reflects what actually happened.

## Things that block the session

- A program that reads **stdin** waits forever; no tool can feed it. Debug a path that takes its
  input from arguments or a fixture.
- A **network call** in the code under inspection is still a network call. Debug against the tests,
  which inject `httpx.MockTransport`, rather than the live command.
- `evaluate_expression` runs arbitrary code in the debuggee. Keep it to reads.
