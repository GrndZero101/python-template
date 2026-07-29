---
name: python-data
description: >-
  Conventions for local data processing with polars, duckdb and pyarrow — lazy versus eager frames
  and why a breakpoint mid-pipeline shows a plan instead of data, explicit duckdb registration
  instead of replacement scans, parquet conventions, and deterministic tests. Use when reading or
  writing parquet or CSV, building a dataframe pipeline, or querying files with SQL.
---

# Local data conventions

Verified against polars 1.43, duckdb 1.5, pyarrow 25.

| Purpose | Package |
|---|---|
| Data analysis / dataframes | `polars` |
| Local data processing, SQL over files | `duckdb` |
| Parquet, interchange | `pyarrow` |

**No pandas.** polars covers the same ground with a stricter schema model, and mixing the two means
two mental models, two null semantics, and a silent copy at every boundary.

## The debugging inversion: lazy frames hold plans, not data

This is the rule that shapes everything else, and it is the analogue of the TUI inversion in
**python-tui**: the standard debugging advice does not work here.

A `LazyFrame` reprs as an opaque pointer:

```text
>>> repr(lf)
'<LazyFrame at 0x1EF4D0312B0>'
```

So a breakpoint in the middle of a lazy pipeline has **nothing to inspect** — the Variables pane
shows an address, not rows. CLAUDE.md bans dicts-as-structs for exactly this reason; a `LazyFrame` in
mid-pipeline is the same problem with a nicer type name.

Three tools instead of hovering:

- **`lf.explain()`** — the optimized query plan as text. Use it to confirm a filter actually got
  pushed down into the scan rather than running after a full read.
- **`lf.head(5).collect()`** — materialize a sample. The cheapest way to answer "what is actually in
  here at this point". Do this from the debug console, not by editing the pipeline.
- **`lf.profile()`** — per-node timings, when the question is *which step* is slow.
- **`lf.collect_schema()`** for column names and dtypes. Do **not** touch `lf.schema` on a lazy frame
  — it warns and forces plan resolution.

### Name the intermediate frames

```python
# Hard to debug: one expression, no inspectable stages.
result = pl.scan_parquet(path).filter(...).group_by(...).agg(...).sort(...).collect()
```

```python
# Debuggable: every stage is a name you can collect a head from.
scanned = pl.scan_parquet(path)
recent = scanned.filter(pl.col("ts") >= cutoff)
totals = recent.group_by("region").agg(pl.col("amount").sum())
result = totals.sort("amount", descending=True).collect()
```

Identical plan, identical performance — lazy evaluation means the intermediates cost nothing until
`collect()`. The second form lets you call `recent.head(5).collect()` from a breakpoint. This is
CLAUDE.md's "name intermediate values" rule, and here it is free.

## Lazy or eager — pick deliberately

- **Lazy** (`scan_parquet`, `scan_csv`, `LazyFrame`) for anything file-backed or in a pipeline. You
  get predicate and projection pushdown, so a filter on one column of a wide parquet reads only what
  it needs.
- **Eager** (`read_parquet`, `DataFrame`) for small in-memory data, and for interactive exploration
  where you want a real `repr` at every step.

Do not mix in one function. Scan lazily, build the pipeline, `collect()` once at the boundary, and
return an eager `DataFrame` to the caller.

For data larger than memory, use the streaming engine:

```python
result = totals.collect(engine="streaming")
```

Note the keyword: `collect(streaming=True)` was removed — it is `engine="streaming"` in polars 1.x.

## duckdb: register tables explicitly

duckdb's Python API resolves an unqualified table name by reaching into the **calling frame's
locals**, which is documented as a replacement scan:

```python
def total_sales() -> int:
    sales = pl.DataFrame({"n": [1, 2, 3]})
    return duckdb.sql("SELECT sum(n) FROM sales").fetchone()[0]  # works. don't.
```

That is precisely what CLAUDE.md's "explicit over dynamic" rule bans. Grep for a table called `sales`
and you find no definition; rename the local variable and the SQL breaks with a table-not-found error
that points at a string, not at the rename. It also cannot be called from a breakpoint, because the
frame it reads is gone.

Register explicitly and inject the connection:

```python
def total_sales(frame: pl.DataFrame, con: duckdb.DuckDBPyConnection) -> int:
    """Return the summed sales figure."""
    con.register("sales", frame)
    return con.sql("SELECT sum(n) AS total FROM sales").fetchone()[0]
```

Now the table name is a literal at a greppable call site, and a test passes `duckdb.connect()` with
whatever frame it likes.

Reach for duckdb over polars when the operation is genuinely more legible as SQL — multi-way joins,
window functions, or `SELECT ... FROM 'data/*.parquet'` across a file glob. Keep the SQL in a module
constant, not inline in the middle of a function, so it can be read and tested on its own.

## pyarrow is the interchange layer, not an API you write against

polars, duckdb and parquet all speak Arrow, which is what makes the handoffs zero-copy. Import
`pyarrow` for the conversion boundary and for parquet metadata; do not build pipelines out of
`pyarrow.compute`.

- polars → duckdb and back goes via Arrow automatically. It is a real dependency of that path even
  when you never import it — a missing `pyarrow` surfaces as a `ModuleNotFoundError` from deep inside
  `to_arrow`, so declare it explicitly in `pyproject.toml`.
- Prefer parquet over CSV for anything intermediate: typed, columnar, compressed, and it keeps the
  schema so the next stage does not re-infer it.
- Snappy for intermediate files, zstd when the file is stored or shipped.
- Partition by the column you filter on most (`year=2026/region=eu/`), so pushdown can skip whole
  directories. Do not partition on a high-cardinality column — thousands of tiny files are slower
  than one large one.

## Structure and injection

Data functions take their inputs as parameters, per CLAUDE.md:

```python
def summarize_sales(source: Path, cutoff: datetime, con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
```

Never read a module-level connection or a global path. Pass the `Path`, pass the connection, pass the
cutoff — then the function is re-runnable from a breakpoint against a fixture file.

Keep the schema in one place as a module constant so the reader knows the shape without running
anything:

```python
SALES_SCHEMA = {"ts": pl.Datetime, "region": pl.String, "amount": pl.Float64}
```

Pass it to `scan_parquet(..., schema=SALES_SCHEMA)` rather than relying on inference. Inference reads
a sample and can differ between files — an int column with one null becomes a float, silently.

## Testing

Deterministic, per CLAUDE.md: no network, fixed inputs.

- Build small frames inline from literal dicts. A five-row frame catches schema and logic bugs; a
  million-row fixture catches neither and slows the suite.
- Write fixture parquet to `tmp_path`, never to the repo.
- **Assert on the schema as well as the values.** `assert result.schema == EXPECTED_SCHEMA` catches
  the dtype drift that value assertions miss — an `Int64` silently becoming `Float64` still compares
  equal by value.
- Use `polars.testing.assert_frame_equal`, which reports the differing column and dtype. A bare
  `assert a.equals(b)` tells you only `False`.
- Sort before comparing anything that came out of a `group_by` — the output order is not guaranteed,
  and an unsorted comparison is a test that passes until it does not.
