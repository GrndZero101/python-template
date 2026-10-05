# Spec: `logs` — pick an entry out of a JSON-lines log, full screen

Add a `logs` command that opens a structured log file in a full-screen terminal view, lets the
user narrow it by level and by text, and writes the entry they choose to stdout — so it composes
with `jq` and the rest of a pipeline.

## Interface

```text
<tool> logs FILE [--level debug|info|warning|error]
```

- `FILE` is a JSON Lines file: one JSON object per line. Blank lines are skipped.
- `--level` / `-l` is the minimum level shown when the screen opens. Default `debug`, which shows
  everything.

Each entry has at least these keys, and may have any others:

| Key | Type | Notes |
|---|---|---|
| `ts` | string | ISO 8601 timestamp, shown as written |
| `level` | string | one of `debug`, `info`, `warning`, `error`, in that order of severity |
| `msg` | string | |

An example, `app.jsonl`:

```text
{"ts": "2026-10-05T09:00:01Z", "level": "info", "msg": "service started", "port": 8080}
{"ts": "2026-10-05T09:00:02Z", "level": "debug", "msg": "cache warmed", "keys": 412}
{"ts": "2026-10-05T09:01:15Z", "level": "warning", "msg": "slow upstream", "upstream": "billing", "ms": 2310}
{"ts": "2026-10-05T09:01:16Z", "level": "error", "msg": "upstream timed out", "upstream": "billing"}
{"ts": "2026-10-05T09:02:00Z", "level": "info", "msg": "Upstream recovered", "upstream": "billing"}
```

## The screen

- A table of the entries shown, in file order: time, level and message.
- A search box. Its text narrows the table to entries whose `msg` contains it, ignoring case.
- A detail pane showing **every** key of the highlighted entry and its value, keys sorted.
- A status line: how many entries are shown out of how many, and the minimum level.

Keys, when the table has focus:

| Key | Does |
|---|---|
| `d` `i` `w` `e` | set the minimum level to debug, info, warning or error |
| `/` | focus the search box |
| `escape` | clear the search and return to the table |
| `enter` | choose the highlighted entry: close the screen and write it to stdout |
| `q` | close the screen and write nothing |

The level and the search combine: from the example, minimum `info` with search `upstream` shows
three entries, the last of them `Upstream recovered`.

## Output

Choosing an entry writes it to stdout as **one line of JSON**, holding exactly the keys and values
the file had for it — nothing added, nothing dropped — and exits 0. Quitting writes nothing and
exits 0. Nothing else ever reaches stdout. The command has no `--output` option: it shows a screen,
not a report.

## Failure

The whole file is read and checked **before** the screen opens. A bad file never draws a screen.

| Situation | Exit | stdout | stderr |
|---|---|---|---|
| `FILE` does not exist or is not a file | 2 | empty | names the file |
| `--level` not one of the four | 2 | empty | names the bad value and the choices |
| A line that is not JSON, not an object, missing `ts`, `level` or `msg`, or with an unknown level | 1 | empty | names the file, the **line number** and what is wrong |
| `FILE` missing from the command line | 2 | empty | the command's help, then the error |

An empty file, or one of only blank lines, is not an error: the screen opens with an empty table.

## Tests that should exist

All offline and deterministic; fixture files go in a temporary directory, and the screen is tested
headless at a fixed size.

- Reading: each malformed case in the failure table, each naming the right line number, counting
  blank lines; extra keys survive.
- Filtering, as plain functions: each minimum level; search ignoring case; the two combined, using
  the example above.
- On the screen: `w` narrows the table to the warning and the error; typing in the search box
  narrows it; `escape` restores it; the status line follows each change.
- Moving the highlight updates the detail pane.
- `enter` returns the highlighted entry exactly as read; `q` returns nothing.
- The command writes a chosen entry to stdout as one JSON line, and nothing when the user quits.
- Each failure row above: correct exit code, empty stdout, and no screen started.
