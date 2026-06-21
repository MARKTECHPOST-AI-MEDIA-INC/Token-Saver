# Token Saver

A portable AI skill for deep work over heavy inputs — PDF analysis, large dataset/log analysis, web scraping, and **web search** — using the fewest tokens possible without losing accuracy.

Ships as a native Agent Skill for Claude, plus paste-in instruction files for ChatGPT and Gemini.

## Versions

This repository keeps **two versions side by side** so you can run them against each other and see the difference:

| Folder | What it is | Use it for |
| --- | --- | --- |
| [`v2/`](v2/) | **Current.** Adds a token-saving **web search** path (`scripts/search.py`, `references/search.md`) and the connector-bridge so it runs inside Claude/Cowork without a shell API key. Packaging fixed so `scripts/` and `references/` install with the skill. | New installs and day-to-day use. |
| [`v1/`](v1/) | **Preserved for reference.** The original skill (PDF / data / scraping only, no web search). Untouched. | A/B comparison and regression testing — see exactly what v2 changed. |

> The loose files at the repository root mirror **v1** and are kept only for backward-compatible links. For the current skill, use the [`v2/`](v2/) folder.

### What changed from v1 → v2

- **New: web search** — `scripts/search.py` (Tavily / Exa / Brave / SerpAPI). Fetch wide, inject narrow: passage-level retrieval (reuses `retrieve.py`'s scorer), cross-source dedup, a total-token budget, and a reversible cache so a full body is pulled (`search.py expand <url>`) only when verification fails. New reference: `references/search.md`.
- **New: connector bridge** — inside an agent with a search connector (e.g. Tavily MCP), call the connector and pipe its JSON into the slicer with `--input -`; no shell `TAVILY_API_KEY` needed. With no key, `search.py` now prints clear guidance instead of a dead end.
- **Updated docs** — `SKILL.md` description now covers web search, with a new routing line, a `search.py` scripts entry, and a new anti-pattern about dumping every search result. `README.md` and `requirements.txt` updated to match.
- **Packaging fix** — the skill packages with the top-level folder named `token-saver/` (matching `name: token-saver` in `SKILL.md`), so `scripts/` and `references/` install alongside `SKILL.md` instead of `SKILL.md` landing alone.

## The idea

**Keep bulk data out of the context window. Do bulk work in code. Bring only a precise, verified slice into the model's reasoning.**

This wins on two fronts at once:

- **Cost** — context is re-sent on every turn, so a 200-page PDF dumped in is re-paid on every follow-up. A small slice is paid once.
- **Accuracy** — a model buried in irrelevant text reasons worse (relevant facts get lost in the middle). A tight, on-point context is more reliable.

So the failure mode is never "too little context" — it's "the wrong little." Token Saver's whole job is to **retrieve precisely** and **verify** the answer against what was retrieved.

## Install / use (v2)

- **Claude (primary):** add the [`v2/`](v2/) folder as a skill (Claude.ai, Claude Code, Cowork, or the API per the Agent Skills docs). Claude reads `SKILL.md` and loads `references/*.md` on demand.
- **ChatGPT:** paste `v2/prompts/chatgpt-instructions.md` into a Custom GPT → Instructions.
- **Gemini:** paste `v2/prompts/gemini-gem.md` into a Gem instruction box.

See [`v2/README.md`](v2/README.md) for the full quickstart, the script reference, and the token/accuracy benchmarks. Testing methodology is in [`v2/TESTING.md`](v2/TESTING.md).

## License

MIT — use, modify, and share freely.
