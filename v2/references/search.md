# Token-saving web search (Tavily / Exa / Brave / SerpAPI)

Search is the worst offender for context bloat: an agent calls a search API, then dumps every result — titles, snippets, and (with advanced depth) full `raw_content` — straight into the prompt. Ten advanced Tavily results can be 20k–40k tokens, and because context is re-sent every turn, that bill repeats on every follow-up.

Same fix as the document path: **search wide, inject narrow.** Use `scripts/search.py`.

## 1. Query → compact, cited slice

```bash
export TAVILY_API_KEY=tvly-...
python scripts/search.py query "GDPR data residency requirements 2026" \\
    --provider tavily --max-results 8 --budget 1200 --per-source 250 -o hits.md
```

What it does, in order (the savings ladder applied to search):

- **Fetch rich, inject thin.** Pulls `raw_content` where the provider gives it, then keeps only the passages that answer the query — never the whole page.
- **Passage-level retrieval.** Reuses `retrieve.py`'s hybrid keyword + (optional) semantic scorer at sentence granularity, so the relevant lines rank, not the boilerplate. Site chrome (cookie/subscribe/ads) is stripped.
- **Cross-source dedup.** The same fact echoed on six sites is paid once; the duplicates are noted as `corroborated by N other source(s)` — grounding value for free.
- **Token budget.** `--budget` caps the total emitted slice. If it would overflow, leads are dropped first, then the lowest-ranked passage — never a silent dump.
- **Reversible (CCR-lite).** Every selected source's full body is cached under `.token_saver_cache/`; the slice carries the path so you can widen on demand.

The stderr coverage report WARNs when query terms match nothing — the cue to widen (`--max-results`, `--budget`) or rephrase before trusting the answer.

## 1b. Inside an agent: use your search connector, not a key

In Claude (or any agent) you usually have a **search connector** (e.g. the Tavily MCP connector) rather than a `TAVILY_API_KEY` env var. Bridge it: call the connector, then pipe its JSON response straight into the slicer with `--input -`.

```bash
# pseudo: <connector returns {query, answer, results:[{title,url,content,raw_content}]}>
echo "$CONNECTOR_JSON" | python scripts/search.py query "your query" --input - --budget 1200
```

This is the path that actually runs inside Claude/Cowork. The connector does the fetching (wide); `search.py` does the slicing (narrow). No key needed in the shell. If the connector returns only snippets, the slice is still deduped and budgeted; pass `--fetch` only when you have a key and want full bodies.

## 2. Widen only when verification fails

```bash
python scripts/search.py expand https://techlaw.blog/article-2   # full cached body
```

Don't pull full bodies up front "just in case." Read the slice; if a check fails, expand the one source you need. This is the escalation ladder for search.

## 3. Snippet-only providers

Brave and most SERP APIs return snippets, not page text. Add `--fetch` to pull main content for each result via the `web_extract.py` path before slicing:

```bash
python scripts/search.py query "..." --provider brave --fetch --budget 1200
```

## 4. Prove it (no key, no network)

Save any provider response to a file and replay it — the harness is offline:

```bash
python scripts/search.py query "..." --input fixtures/tavily.json --count-only
```

Reports naive-dump tokens vs the sliced tokens so the savings are auditable, the same way `eval/measure_tokens.py` does for PDFs.

## Why it compounds

| Turns | Naive (dump every result each turn) | search.py (slice + cached prefix) |
| --- | --- | --- |
| 1 | all results | small slice |
| 5 | 5× all results | 5 small slices |

A search-heavy agent does this on every tool call. Slicing once per call, with dedup across calls in the same session (shared `.token_saver_cache/`), is where the bill actually drops.
