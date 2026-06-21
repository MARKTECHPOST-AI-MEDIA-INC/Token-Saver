---
name: token-saver
description: Accuracy-preserving, token-minimal processing of heavy inputs. Use this skill whenever a task involves analyzing PDFs, reading or summarizing long documents, exploring large datasets/CSVs/logs/JSON, scraping or crawling web pages, running web searches (Tavily/Exa/Brave/SerpAPI), or any "deep analysis" over bulk data — even if the user never mentions tokens or cost. Apply it proactively BEFORE loading big files or many pages into context. It keeps the model's context small by doing bulk work in code, while protecting accuracy with precise retrieval, mandatory grounding/citations, and a verify-then-widen escalation loop — so answers get cheaper AND more reliable, not one at the expense of the other.
---

# Token Saver

Do deep work over heavy inputs (PDFs, large datasets, scraped pages) using the fewest tokens possible without losing accuracy. Both goals are served by the same move.

## The principle

**Keep bulk data out of the context window. Do bulk work in code. Bring only a precise, verified slice into the model's reasoning.**

## Why this raises accuracy and cuts cost (they are not in tension)

Two facts that point the same way:

- **Cost:** anything in context is re-sent on every turn. A 200-page PDF (~150k tokens) dumped in is re-paid on every follow-up question — not once.
- **Accuracy:** a model reasons worse, not better, when buried in irrelevant text. Relevant facts get lost in the middle; the model pattern-matches to noise. A tight, on-point context produces more reliable answers than a bloated one.

So the failure mode is never "too little context." It is "the wrong little." The entire job is therefore: **retrieve precisely** (don't miss the relevant part), and **verify that the answer is actually grounded** in what you retrieved (catch it when you did miss). Get those right and cheap = accurate.

## The accuracy contract (non-negotiable)

- **Ground and cite.** Every factual claim must trace to a retrieved span — cite it (`[page 42]`, `row 1184`, source URL). If you can't point to where it came from, it doesn't go in the answer.
- **Abstain or widen — never fill gaps from priors.** If the retrieved slice doesn't support an answer, do NOT guess from training knowledge. Either say "not present in the retrieved material" or escalate the retrieval (ladder below). Hallucination is the #1 accuracy risk of aggressive trimming; grounding is the defense.
- **Verify before finalizing.** Re-check the answer against the slice: is every claim cited? Did retrieval look in the right places (the section the outline points to, all rows for a "total", the defined term used on another page)? If a check fails, widen and redo. Don't present an unverified answer.

## The workflow

Same six steps for PDFs, data, and scraping. Per-domain commands are in `references/`.

1. **Inventory cheaply.** Structure before content: page count + outline/headings + defined terms + footnotes (PDF); row count + schema + sample rows (data); sitemap/links (web). This is tiny and is also an accuracy safeguard — it tells you where the relevant material lives so retrieval doesn't miss it.
2. **Retrieve precisely (don't miss).** Pull the specific slice the task needs, using:
   - **Structural anchors** — always include the outline/headings and any defined terms, footnotes, or cross-references. This prevents the classic miss (a term defined on p.3 but used on p.80).
   - **Hybrid matching** — keyword and semantic when available, so synonyms don't slip through. Keyword-only is the fallback.
   - **Neighbor expansion** — include the pages/rows immediately around each hit, and follow explicit cross-references ("see §4.2"). Use `scripts/retrieve.py` — it does all three and prints a coverage report.
3. **Extract with code.** Pull exactly that slice; strip boilerplate; convert tables to CSV; emit compact JSON/CSV/plain text. Bulk stays in code; only the slice is surfaced.
4. **Persist to disk.** Write extracted text/records to a file; refer to it by path. Never re-paste or re-extract. (And cache the stable context — see step on savings.)
5. **Answer, grounded, with citations.** Reason only over the slice. Cite every claim.
6. **Verify + escalate if needed.** Run the contract's checks. If anything fails, climb the ladder and redo — but only as far as needed.

## The escalation ladder (the accuracy ↔ savings dial)

Start tight; widen only when verification flags a gap. This is what makes the skill adaptive: cheap on easy documents, thorough on hard ones, never blindly maximal.

1. **Targeted slice** — top matching pages/rows + anchors + neighbors. (cheapest)
2. **Wider slice** — raise top-k, add more neighbors, pull the full matched section.
3. **Section/chapter read** — when the answer spans a whole region.
4. **Map-reduce the whole input** — chunk → extract/summarize each chunk to disk → combine. Use this only when the task genuinely requires the entire document; even then the full text never sits in context at once. (most thorough)

Stop at the first rung where verification passes.

## Maximizing token savings (the savings ladder)

Apply in roughly this order; details in `references/savings.md`.

1. **Bulk in code, not context** — the principle above. Biggest lever.
2. **Cache the stable context** — put the system prompt, skill instructions, and any context that must persist behind prompt caching (`cache_control`). Re-sent cached tokens cost a fraction of fresh ones; this dominates multi-turn cost. Stacks with precise retrieval — it doesn't replace it.
3. **Strip and compress** — drop boilerplate/whitespace, tables → CSV, terse structured output, no restating the input back to the user.
4. **Reuse artifacts** — extract once to disk; read only the needed slice on later turns.
5. **Offload to a separate context** — run heavy extraction in a sub-agent/separate thread whose tokens don't pollute the main conversation (where available).
6. **Budget** — set a per-task token ceiling; if a slice would blow it, retrieve harder rather than dumping more.

## Routing to detail

Load only the file you need:

- **PDFs / long documents** → `references/pdf.md`
- **Datasets, CSVs, logs, JSON, codebases** → `references/data-analysis.md`
- **Web scraping / crawling** → `references/scraping.md`
- **Web search (Tavily / Exa / Brave / SerpAPI)** → `references/search.md`
- **Grounding, retrieval-that-doesn't-miss, verification** → `references/accuracy.md`
- **Caching and the savings ladder in depth** → `references/savings.md`

## Scripts

Run them; they don't load into context — run with `--help`:

- `scripts/retrieve.py` — precise, citable slice: structural anchors + hybrid match + neighbor expansion + coverage report. The accuracy workhorse.
- `scripts/pdf_inspect.py` — inventory, outline, text/page extraction, search, tables, scanned-page detection, chunking for map-reduce.
- `scripts/web_extract.py` — main-content/clean text, selector field extraction, links.
- `scripts/search.py` — token-saving web search: fetch wide, inject narrow. Passage-level retrieval (reuses retrieve.py's scorer), cross-source dedup, total-token budget, and a reversible cache so full bodies are pulled (`search.py expand <url>`) only when verification fails. Tavily / Exa / Brave / SerpAPI via key; or, inside an agent with a search connector (e.g. Tavily MCP), call the connector and pipe its JSON in with `--input -` (no shell key needed). Offline `--input <file>` replay for auditing savings.

## Degraded mode (no code execution)

Same principle, applied by hand: read the outline/search results first; ask the user for the specific pages/sections/fields; process one chunk at a time with a short running summary; cite as you go; and if you can't ground a claim, say so and request the missing part rather than guessing.

## Anti-patterns

- Dumping a whole PDF/dataset/page into context for a question touching a small part.
- Answering an uncited claim, or filling a gap from prior knowledge instead of widening retrieval. (accuracy killer)
- Trusting a mangled table dump — extract to CSV and verify instead.
- Sampling rows when the task asks for a total/exhaustive answer — aggregate all rows in code. (accuracy killer)
- Rasterizing every page of a text PDF; reading raw HTML when a selector would do.
- Re-pasting the same block across turns instead of caching/persisting it.
- Crawling many pages and holding all raw markup at once.
- Dumping every web-search result (titles + snippets + full `raw_content`) into context — slice to the answering passages with `search.py`, dedup across sources, and expand a full body only on demand.

## Cross-platform

Strategy is platform-independent; packaging differs. This folder is a native Agent Skill for Claude. For other assistants, paste the equivalent file as system/instructions: `prompts/chatgpt-instructions.md`, `prompts/gemini-gem.md`. Without code execution, fall back to Degraded mode; savings are largest where code execution exists, because that is what lets bulk data bypass context entirely.
