# Datasets, CSVs, logs, JSON, codebases

The golden rule: **the rows never enter context - only a checkable result does.**
Do the work in code (pandas, SQL, grep, jq) and surface a small aggregate or sample.

## 1. Inventory cheaply

Schema and shape before any rows:

```python
import pandas as pd
df = pd.read_csv("data.csv")
print(df.shape)            # (rows, cols)
print(df.dtypes)           # schema
print(df.head(3))          # a few sample rows - NOT the whole file
print(df.isna().sum())     # data-quality signal
```

For huge files, read in chunks (`chunksize=`) or just the header, and let SQL /
DuckDB scan on disk rather than loading everything into memory or context.

## 2. Answer with an aggregate, not the rows

```python
df.groupby("region")["revenue"].sum().sort_values(ascending=False)
df.query("status == 'failed'").shape[0]
```

Return the resulting table/number. A million rows become a few lines.

## Accuracy killer: do NOT sample when the task is exhaustive

If the question is a **total, count, max, or "every X"**, aggregate over **all**
rows in code. Sampling rows into context and eyeballing them is the classic way
to get a confidently wrong answer. Sampling is fine only for "show me examples."

## Logs

Filter and count with the tool, surface the summary:

```bash
grep -c "ERROR" app.log
grep "ERROR" app.log | awk '{print $5}' | sort | uniq -c | sort -rn | head
```

Bring the histogram into context, not 2 GB of log lines.

## JSON

Use `jq` to project just the fields you need before reading:

```bash
jq '.items[] | {id, status, total}' big.json | head
jq '[.items[] | select(.status=="open")] | length' big.json
```

## Codebases

Treat the repo like a document: inventory the tree, then open only the relevant
files. Find the right files with search, don't read the whole tree:

```bash
git ls-files | head -50            # structure
grep -rn "def authenticate" src/   # locate, then open just those files
```

## Verify before answering

- Aggregates were computed over the full dataset, not a sample (for total/count tasks).
- The number traces to a specific query/filter you can show (`row 1184`, that `groupby`).
- NaNs / type coercions were handled (an `isna` or `dtype` check), not silently dropped.
- If a field needed isn't in the schema, say so - don't infer it from priors.
