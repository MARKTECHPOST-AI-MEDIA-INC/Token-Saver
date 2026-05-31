# Testing & Results

This document records how Token Saver was verified — that the scripts run end to
end **and** that the anchored-slice approach actually reduces the tokens sent to
the model. Everything here is reproducible from a clean checkout in a few minutes.

## TL;DR

| Document | Naive (full doc in context) | Token Saver (anchored slice) | Input tokens saved |
| --- | --- | --- | --- |
| 29-page PDF, 2 questions | 6,282 | 2,238 | **64%** |
| 150-page PDF, 1 question | 17,212 | 536 | **96%** |

The slice stays roughly constant while the naive cost grows linearly with the
document, so **savings increase with document size**. Across multi-turn chats the
gap compounds, because the naive approach re-sends the whole document every turn
while the slice does not.

All seven automated checks pass:

```
RESULT: 7 passed, 0 failed
29-page doc: 64% input tokens saved
150-page doc: 96% input tokens saved
```

## How to reproduce

```bash
# from the repo root
python -m venv .venv && source .venv/bin/activate # see "Environment" note below
pip install -r requirements.txt
pip install -r tests/requirements-test.txt # reportlab, for building fixtures

python tests/make_fixtures.py # writes tests/fixtures/small.pdf (29p) + big.pdf (150p)
python tests/selftest.py # runs all checks; exit code 0 = all pass
```

No API key is required: the token measurement uses `measure_tokens.py --dry-run`,
which counts the exact bytes that would be sent for the naive vs. slice paths.

## What is tested

`tests/selftest.py` runs the **real scripts** (no mocks) against deterministic
fixtures and asserts on their output:

| # | Check | What it proves |
| --- | --- | --- |
| 1 | `pdf_inspect.py info` reports 29 pages | PDF inventory works |
| 2 | `pdf_inspect.py search "GDPR"` returns page 20 | phrase search lands on the right page |
| 3 | `retrieve.py` ranks the revenue page (p12) **#1** | retrieval finds the true needle, not filler |
| 4 | `retrieve.py` warns **"matched NOTHING"** on an off-topic query | the abstain/escalate safety behavior fires |
| 5 | `measure_tokens.py --dry-run` saves >40% on 29p and >90% on 150p, and the 150p saving exceeds the 29p saving | the slice is smaller than the full doc, and savings scale with size |

### Fixtures (`tests/make_fixtures.py`)

Deterministic PDFs with **known needle content on known pages**, so the asserts
are exact rather than approximate:

- `small.pdf` — 29 pages: revenue-recognition needle on **p12**, GDPR needle on
**p20**, a `see section 4.2` cross-reference on **p1**, filler everywhere else.
- `big.pdf` — 150 pages: a single revenue-recognition needle on **p80**, filler
elsewhere. Used to show savings grow with document size.

## Measuring against the live API (optional)

The numbers above use `--dry-run` (char/4 estimate, no network). To measure with
the real tokenizer and real model answers, set a key and use the other two modes
of `eval/measure_tokens.py`, which share the same slice-building code path:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
printf "What is the revenue recognition policy for SaaS?\n" > q.txt

# exact input-token count via the API token counter, no model run:
python eval/measure_tokens.py --pdf tests/fixtures/big.pdf --questions q.txt --count-only

# full A/B: real token usage in/out + both answers side by side:
python eval/measure_tokens.py --pdf tests/fixtures/big.pdf --questions q.txt
```

## Environment notes

- Verified on **macOS (Darwin)** with **Python 3.9**.
- **Avoid pre-release Python (3.13+ alphas).** On Python 3.15.0a7, `Pillow` (a
transitive dependency of `pdfplumber`) has no prebuilt wheel and fails to
compile, which breaks `pip install -r requirements.txt`. Use a stable 3.9–3.12
interpreter.

## Known limitation surfaced during testing

`retrieve.py` keeps any query token longer than two characters
(`scripts/retrieve.py`, `keyword_scores`), so the stopword **"for"** is treated
as a real term and can inflate the score of filler pages. In test #3 the correct
page still ranked #1, so answers are unaffected, but the slice may pull a few
extra neighbor pages (slightly less saving). A short stopword list — or requiring
`len(token) > 3` — would tighten this.
