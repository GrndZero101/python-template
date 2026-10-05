# Spec: `spend` — total a cloud billing export by service or account

Add a `spend` command that reads a billing export and shows where the money went: a total per
service or per account, largest first, over an optional date window.

## Interface

```text
<tool> spend FILE [--since DATE] [--until DATE] [--by service|account] [--top N] [--output table|json]
```

- `FILE` is a `.csv` or `.parquet` billing export (below).
- `--since` and `--until` are ISO dates, `YYYY-MM-DD`, both **inclusive**. Either may be omitted;
  omitting both counts the whole file.
- `--by` chooses what to group by. Default `service`.
- `--top` / `-n` is how many groups to show. Default 5, minimum 1. The groups beyond it are combined
  into a single row named `(other)`, shown last. With N groups or fewer there is no `(other)` row.
- `--output` / `-o` follows the existing scaffold option, including its environment variable.

## The input

Four columns, by name, in any order; any other column is ignored:

| Column | Type | Notes |
|---|---|---|
| `date` | date | `YYYY-MM-DD` in a CSV |
| `account` | string | |
| `service` | string | |
| `cost_cents` | integer | US cents. **Negative** for a credit or refund. |

Money stays in integer cents from the file to the output, so no total is ever a float.

An example, `sample.csv`:

```text
date,account,service,cost_cents
2026-09-01,prod,compute,12000
2026-09-01,prod,storage,3000
2026-09-02,staging,compute,4000
2026-09-02,prod,network,1500
2026-09-03,prod,compute,8000
2026-09-03,staging,storage,500
2026-09-04,prod,support,2500
2026-09-04,prod,compute,-2000
```

## The result

- One row per group: its name, its total in cents, and its **share** of the grand total as a
  percentage rounded to one decimal place. Shares are rounded independently, so they need not sum
  to exactly 100.
- Groups are ordered by total, largest first; equal totals by name, ascending. `(other)` is last
  whatever its total.
- When the grand total is zero or negative, a share means nothing: every share is null.
- The window reported is the earliest and latest `date` among the rows counted, not the flags.

Worked from `sample.csv`:

- `spend sample.csv --top 2` → `compute` 22000 (74.6%), `storage` 3500 (11.9%), `(other)` 4000
  (13.6%); grand total 29500; window 2026-09-01 to 2026-09-04.
- `spend sample.csv --by account --since 2026-09-02 --until 2026-09-03` → `prod` 9500 (67.9%),
  `staging` 4500 (32.1%); grand total 14000; window 2026-09-02 to 2026-09-03.

## Output

- **table**: titled with the grouping and the window; columns for the name, the total in dollars to
  two decimal places (`$220.00`, `-$20.00`), and the share (`74.6%`, or `—` when null); a final
  row with the grand total.
- **json**: one object — `by`, `since`, `until`, `total_cents`, and `groups`, a list of
  `{"name", "total_cents", "share_pct"}`. Cents are integers; `share_pct` is a number or `null`.
  `since` and `until` are ISO dates, or `null` when no row was counted.

No row in the window is not an error: exit 0, an empty table or `"groups": []`, a total of 0.

## Failure

| Situation | Exit | stdout | stderr |
|---|---|---|---|
| `FILE` missing, or not `.csv` / `.parquet` | 2 | empty | names the file and the expected form |
| `--since` or `--until` not `YYYY-MM-DD`, `--top` below 1, `--by` not a choice | 2 | empty | names the bad value and the expected form |
| `--since` later than `--until` | 2 | empty | names both dates |
| The file cannot be read as the input above: a missing column, a `cost_cents` that is not an integer, a `date` that is not a date | 1 | empty | names the file and the cause |
| `FILE` missing from the command line | 2 | empty | the command's help, then the error |

## Tests that should exist

All offline and deterministic; fixture files go in a temporary directory.

- Both worked examples above, with their expected values written by hand from the rows.
- The window is inclusive at both ends, and each bound works alone.
- Ordering: by total descending, ties by name; `(other)` last even when it is the largest.
- `--top` equal to the number of groups produces no `(other)` row.
- Credits reduce a group's total; a grand total of zero or below gives null shares.
- An empty window gives an empty result **with the same columns and types** as a full one.
- The result's column types are asserted, not just its values: a total stays an integer.
- The command reads a CSV and a parquet file of the same rows to the same result.
- JSON keeps cents as integers.
- Each failure row above: correct exit code, empty stdout.
