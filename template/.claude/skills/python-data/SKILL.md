---
name: python-data
description: >-
  Recipes for a CLI command that processes local data with polars, and duckdb when SQL reads
  better — reading CSV or parquet with a declared schema, a lazy pipeline of named stages collected
  once, why a breakpoint mid-pipeline shows a plan instead of data, explicit duckdb registration,
  and deterministic tests with schema assertions. Use when a command reads, summarizes or writes
  CSV or parquet files, builds a dataframe pipeline, or queries files with SQL.
---

# Data command recipes

A data command is an ordinary command of this CLI — **python-cli-modern** owns the command shape,
settings and output — whose work is a polars pipeline. Verified against polars 1.44, duckdb 1.5
and pyarrow 25.

**No pandas.** polars covers the same ground with a stricter schema model, and mixing the two means
two mental models, two null semantics, and a silent copy at every boundary.

## Recipe: add a data command

Copy the worked command rather than writing one from scratch:

```bash
uv add polars
cp .claude/skills/python-data/reference/summary.py src/<package>/
cp .claude/skills/python-data/reference/test_summary.py tests/
```

They pass the gate and their tests exactly as copied (a generation test proves it). `summary`
reads a CSV or parquet file of request records and prints requests, 5xx responses and p95 duration
per service. Then:

1. **Register it in `src/<package>/cli.py`**, beside `about`, as "Recipe: add a command" in
   python-cli-modern shows: `app.command("summary")(summary_command)`.
2. **Rename and reshape it.** Change `RECORD_SCHEMA` to your input's columns, `summarize` to your
   pipeline, and `SUMMARY_SCHEMA` and `build_summary_table` to its output. Keep the layers:
   `parse_records_path` validates the argument, `scan_records` reads, `summarize` computes,
   `emit_summary` renders, and the command only delegates.
3. **Rewrite the test's five-row `RECORDS` and its `EXPECTED`**, by hand from the rows, not by
   running the pipeline and pasting what it printed.
4. **Check:** `uv run pytest`, then `prek run --all-files`.

## Rules every data command follows

- **Declare the schema; never infer it.** Inference reads a sample and can differ between files —
  an int column with one null becomes a float, silently.
- **Match the schema by name.** An export reorders and adds columns, so read as `scan_records`
  does: `scan_csv(path, schema_overrides=SCHEMA).select(list(SCHEMA))`, and
  `scan_parquet(path, schema=SCHEMA, extra_columns="ignore")`. Never `scan_csv(path, schema=...)`:
  it matches by **position** and ignores the header, so a reordered file fails, or — when two
  string columns trade places — reads without error under the wrong names. Both forms reject a
  value of the wrong type; a `.cast()` after reading would truncate `1.5` to `1` instead.
- **Scan lazily, collect once.** The pipeline takes a `LazyFrame` and returns a collected
  `DataFrame`; the command never sees a lazy frame. Lazy scans push a filter or a column selection
  down into the read, so a filter on one column of a wide parquet reads only what it needs.
- **Name every stage.** One chained expression gives a breakpoint nothing to inspect; named stages
  cost nothing until `collect()`, and each can be sampled from the debug console. This is
  CLAUDE.md's "name intermediate values" rule, and here it is free.
- **Sort after every `group_by`.** Its output order is not guaranteed, so an unsorted result is a
  test that passes until it does not.
- **A bad file is a runtime failure, exit 1**: catch `pl.exceptions.PolarsError` in the command,
  name the file and the cause on stderr, as `summary_command` does. A bad *argument* — a missing
  file, the wrong extension — is a usage error from the argument's parser, exit 2.
- **Inputs are parameters.** Pass the `Path`, the connection, the cutoff date; never a module-level
  connection or path. Then a function re-runs from a breakpoint against a fixture file.

## Debugging: a lazy frame holds a plan, not data

A `LazyFrame` reprs as a plan, so a breakpoint mid-pipeline shows no rows. From the debug console:

- **`stage.head(5).collect()`** — materialize a sample. The cheapest way to answer "what is
  actually in here at this point".
- **`stage.collect_schema()`** — column names and dtypes, without running the query.
- **`stage.explain()`** — the optimized plan as text. Use it to confirm a filter was pushed down
  into the scan rather than run after a full read.

`LazyFrame.profile()` is deprecated since polars 1.43: per-node timings mislead under the streaming
engine. To find a slow stage, time `collect()` on successive stages instead.

For data larger than memory, `collect(engine="streaming")`. `collect(streaming=True)` was removed.

## duckdb: when SQL reads better

Reach for duckdb when the operation is genuinely more legible as SQL — multi-way joins, window
functions, or `FROM 'data/*.parquet'` across a file glob. Converting between it and polars goes
through Arrow, so add both:

```bash
uv add duckdb pyarrow
```

Without `pyarrow`, `register` fails deep inside polars with `No module named 'pyarrow'`.

**Register tables explicitly, and pass the connection in.** duckdb resolves an unregistered table
name by reaching into the calling frame's local variables — a replacement scan. That is exactly the
dynamic lookup CLAUDE.md bans: grep finds no definition of the table, and a rename breaks a string.

```python
TOTALS_BY_REGION = (
    "SELECT region, sum(amount)::BIGINT AS total FROM sales GROUP BY region ORDER BY region"
)


def totals_by_region(frame: pl.DataFrame, con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Return one row per region."""
    con.register("sales", frame)
    return con.sql(TOTALS_BY_REGION).pl()
```

- **SQL in a module constant**, never assembled with an f-string. A value goes in as a parameter:
  `con.execute("SELECT ... WHERE region = ?", [region])`.
- **`fetchone()` returns `None` when there is no row**, so `ty` rejects `fetchone()[0]`. Check it:

  ```python
  row = con.execute("SELECT sum(amount) FROM sales").fetchone()
  if row is None:
      msg = "sum() returned no row"
      raise RuntimeError(msg)
  ```

- **Cast aggregates in the SQL.** duckdb's `sum` of integers is a `HUGEINT`, which reaches polars
  as `Decimal(38, 0)`; `::BIGINT` makes it an `Int64`. The schema assertion in the test catches it
  either way.
- `.pl(lazy=True)` hands the result to polars as a `LazyFrame`, to continue a lazy pipeline.

A test passes `duckdb.connect()` — an in-memory database — and whatever frame it likes.

## Files

- **Parquet over CSV** for anything intermediate: typed, columnar, compressed, and it keeps the
  schema, so the next stage does not re-infer it. `write_parquet` needs no `pyarrow`.
- Snappy for intermediate files, zstd when the file is stored or shipped.
- Partition by the column you filter on most (`year=2026/region=eu/`), so pushdown skips whole
  directories. Never on a high-cardinality column: thousands of tiny files are slower than one.

## Testing

`reference/test_summary.py` is the model.

- **Build small frames inline** from literal dicts, with the declared schema. A five-row frame
  catches schema and logic bugs; a million-row fixture catches neither and slows the suite.
- **Write fixture files to `tmp_path`**, never to the repo, and run the command on them through
  `main`, once per format it reads.
- **Assert the schema as well as the values.** `assert result.schema == SUMMARY_SCHEMA` catches an
  `Int64` silently becoming `Float64`, which still compares equal by value.
- **`polars.testing.assert_frame_equal`**, which names the differing column and dtype. A bare
  `assert a.equals(b)` says only `False`.
- **An empty input** gives an empty result with the same schema, not an error. Test it.
