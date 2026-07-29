---
name: python-tui
description: >-
  Conventions for Textual terminal user interfaces — how to debug when print and pdb are unavailable
  because the app owns the terminal, keeping logic out of widgets so it stays testable, workers for
  blocking work, and testing with the Pilot harness. Use when writing or changing a Textual App,
  Screen or Widget, or when debugging a TUI.
---

# Textual TUI conventions

## Debugging: the exception to everything else

**A Textual app owns the terminal. `print` and `pdb` corrupt the display.** Anything written to
stdout lands in the middle of the rendered frame, and a `pdb` prompt fights the app for the same
screen. The base debugging advice in CLAUDE.md assumes a program that can write to a stream; this is
the one project type where it does not hold.

Two terminals. In the first:

```bash
textual console
```

In the second, run the app in dev mode:

```bash
textual run --dev app.py
```

Now `print` is *restored* — it goes to the console window, not the display — and so are Textual's own
log messages. Inside the app prefer the `log` method, which renders structures readably:

```python
class Viewer(App):
    def on_mount(self) -> None:
        self.log("mounted", rows=len(self.rows))
        self.log(self.tree)  # the whole widget tree
```

`self.log` is available on `App` and on every `Widget`. `self.log(self.tree)` is the fastest way to
answer "why is my widget not where I expected".

Filter noise with `textual console -x EVENT -x SYSTEM`, or narrow to what you want with
`textual console -i CUSTOM`.

For stepping through with a real debugger, attach to the process rather than breaking into the
terminal — set `justMyCode: false` and attach via `debugpy`, and put your breakpoints in the plain
functions described next, not in `render` or `compose`.

## Keep the logic out of the widgets

This is the rule that makes everything else possible, and it is the base rules applied unchanged.

A `Widget` subclass can only be exercised inside a running app. A plain module-level function can be
called from a breakpoint with literal arguments. So put the work in the function:

```python
# domain.py — no Textual import anywhere in this file
def summarize(rows: list[Row]) -> Summary:
    """Reduce rows to the figures the table displays."""
```

```python
# widgets.py
class SummaryPanel(Static):
    def on_mount(self) -> None:
        self.update(render_summary(summarize(self.rows)))
```

Most of the test suite then never starts an app. If a bug can only be reproduced by driving the UI,
that usually means logic has leaked into a widget.

- Event handlers (`on_*`, `@on`) unpack the event and delegate — same shape as a CLI's
  unpack-and-delegate handler.
- Reactive attributes hold display state, not domain state.
- No business rules in `compose` or `render`.

## Blocking work goes in a worker

Anything slow in a handler freezes the UI, including input. Use a worker:

```python
@work(exclusive=True)
async def load_records(self) -> None:
    """Fetch records without blocking the UI."""
    rows = await fetch_rows(self.client)
    self.query_one(DataTable).add_rows(rows)
```

- `exclusive=True` cancels a previous run of the same worker — the right default for
  reload-on-keypress.
- Use `thread=True` for blocking (non-awaitable) calls.
- Only touch widgets from the app's own task. `call_from_thread` when in a threaded worker.

Note that `@work` decorates a **method**, which is not a nested `def` — `check_nested_defs.py`
resets its enclosing scope at a `class` body, so this is not a violation.

## Testing with Pilot

`run_test()` runs the app headless — no terminal updates, all other logic live. It is an async
context manager yielding a `Pilot`:

```python
async def test_filter_narrows_the_table() -> None:
    app = Viewer(rows=SAMPLE_ROWS)
    async with app.run_test() as pilot:
        await pilot.press("f", "o", "o")
        await pilot.pause()
        table = app.query_one(DataTable)
        assert table.row_count == 2
```

- The test must be `async`; the project needs `pytest-asyncio` (or `anyio`) configured.
- `await pilot.pause()` after an interaction, to let pending messages settle before asserting.
  Missing this is the usual cause of a test that passes alone and fails in a suite.
- `pilot.press(...)`, `pilot.click(selector)`, `pilot.hover(selector)` drive the app. Assert on
  **app and widget state** via `query_one`, not on rendered characters.
- `run_test(size=(80, 24))` pins the terminal size, so layout assertions are deterministic.

For deliberate visual regression testing, `pytest-textual-snapshot` compares SVG screenshots. Use it
for layout you actually care about keeping, not by default — snapshots fail on every intentional
style change, and a suite full of them stops being read.

## Structure

```text
src/pkg/
  domain.py    # pure logic, no Textual import
  widgets.py   # Widget subclasses
  screens.py   # Screen subclasses
  app.py       # the App, bindings, CSS path
  app.tcss     # styles
```

Keep styles in a `.tcss` file with `CSS_PATH`, not in a `DEFAULT_CSS` string — the editor can
highlight it and the diff stays readable.

Give the app a real entrypoint too, so it is a command and not just a runnable file. The
`main(argv) -> int` contract from **python-cli** still applies at that boundary: parse arguments,
construct the app, call `run()`, return an exit code.
