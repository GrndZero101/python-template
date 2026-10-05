---
name: python-tui
description: >-
  Recipes for a CLI command that opens a full-screen Textual interface — a table to browse, a
  picker, a live view — with its logic in plain functions, handlers that unpack and delegate,
  logging that does not corrupt the screen, the Textual console for debugging, and headless Pilot
  tests. Use when a command needs an interactive terminal screen, or when writing or debugging a
  Textual App, Screen or Widget.
---

# TUI command recipes

A TUI is one command of this CLI — **python-cli-modern** owns the command shape, settings and
errors — that opens a full-screen Textual app instead of printing a result. Verified against
Textual 8.2 and pytest-asyncio 1.4.

## Recipe: add a TUI command

Copy the worked command rather than writing one from scratch:

```bash
uv add textual
uv add --dev pytest-asyncio textual-dev
cp .claude/skills/python-tui/reference/rows.py .claude/skills/python-tui/reference/browse.py src/<package>/
cp .claude/skills/python-tui/reference/test_rows.py .claude/skills/python-tui/reference/test_browse.py tests/
```

They pass the gate and their tests exactly as copied (a generation test proves it). `browse` shows
a CSV file as a table that narrows as you type. Then:

1. **Register it in `src/<package>/cli.py`**, beside `about`, as "Recipe: add a command" in
   python-cli-modern shows: `app.command("browse")(browse_command)`.
2. **Rename and reshape it.** The logic goes in the Textual-free module (`rows.py`); the app in
   `browse.py` only lays out widgets and forwards events to it.
3. **Test the logic as plain functions** (`test_rows.py`), and the app through Pilot
   (`test_browse.py`): one test per interaction that matters, not per widget.
4. **Check:** `uv run pytest`, then `prek run --all-files`.

`pytest-asyncio` runs the async Pilot tests; `textual-dev` provides `textual console`.

## Rules every TUI command follows

- **Logic in a module with no Textual import.** A widget runs only inside an app, so a debugger
  cannot call it with literal arguments and a test must start an app to reach it. A plain
  function has neither problem. If a bug can only be reproduced by driving the UI, logic has leaked
  into a widget.
- **Handlers unpack the event and delegate**, like a command: `@on(Input.Changed)` on a method
  named for what it does, never business rules in `compose`, `render` or `on_mount`. Prefer `@on`
  to a bare `on_input_changed` name: the decorator is greppable and says which message it takes.
  A handler that does not need its event omits the parameter; Textual allows it, and the gate's
  unused-argument rule then has nothing to report.
- **Read and validate before `run()`.** A missing or malformed input is an ordinary CLI error,
  exit 1 on stderr, as `browse_command` does — not an exception inside a screen.
- **Nothing writes to the terminal while the app runs.** Textual redirects `sys.stdout` and
  `sys.stderr`, but loguru's sink holds the real stderr, so a loguru call from a handler draws over
  the screen. Inside the app use `self.log(...)`; loguru before `run()` and after it is fine.
- **A TUI command has no `--output`**: it shows a screen, not data. A picker that returns a choice
  ends with `self.exit(choice)`; the command writes the value `run()` returns to stdout after the
  screen has closed.
- **The app runs in one function, `run_screen`**, which the command calls and nothing else does. A
  test through `main` replaces it with `monkeypatch.setattr`, as `test_browse.py` does, to prove a
  bad file starts no screen and — in a picker, whose `run_screen` returns the choice — that the
  choice reaches stdout. The app itself is tested through Pilot.
- **Class-level `BINDINGS` is annotated** `ClassVar[list[BindingType]]`, or the gate reports a
  mutable class default.
- **Blocking work goes in a worker**: `@work(exclusive=True)` on an async method, or
  `@work(thread=True)` for a blocking call. Anything slow in a handler freezes input. From a thread
  worker, touch widgets only through `self.call_from_thread`.
- **Styles in a `.tcss` file** named by `CSS_PATH` once there are any, not a `DEFAULT_CSS` string,
  so the editor can highlight it and the diff stays readable.

## Debugging: the app owns the terminal

`print` and `pdb` corrupt the display: whatever they write lands in the middle of the frame. Use
the Textual console instead. In one terminal:

```bash
uv run textual console
```

In another, run the command with the devtools on — `TEXTUAL=devtools,debug` is what
`textual run --dev` sets, and it works through this project's own script:

```bash
TEXTUAL=devtools,debug uv run <script> browse hosts.csv
```

`self.log(...)` and `print` now appear in the console, with Textual's own events.
`self.log(self.tree)` shows the whole widget tree, the fastest answer to "why is my widget not
where I expected". Narrow the noise with `textual console -x EVENT -x SYSTEM`. Without a second
terminal, `TEXTUAL_LOG=textual.log` appends the same logs to a file.

To step through code, step through the logic module through its tests, as the **python-debug**
skill describes; that is why the logic lives there.

## Testing with Pilot

`app.run_test()` runs the app headless — no terminal, every other part live — and yields a `Pilot`:

```python
@pytest.mark.asyncio
async def test_typing_narrows_the_table() -> None:
    app = BrowseApp(SOURCE)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("e", "u")
        await pilot.pause()
        assert app.query_one(DataTable).row_count == 2
```

- **Mark each async test `@pytest.mark.asyncio`.** Without it the test fails with "async def
  functions are not natively supported".
- **`await pilot.pause()` after an interaction**, so pending messages settle before the assertion.
  Missing it is the usual cause of a test that passes alone and fails in the suite.
- **Assert on widget state** through `query_one`, never on rendered characters.
- **Pin the size**, `run_test(size=(80, 24))`, so layout is the same on every machine.
- `pytest-textual-snapshot` compares SVG screenshots. Use it only for layout you mean to keep:
  every intentional style change fails it, and a suite full of snapshots stops being read.
