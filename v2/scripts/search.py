#!/usr/bin/env python3
"""search.py - token-saving web search (Tavily / Exa / Brave / SerpAPI).

The anti-pattern this kills: `tavily.search(q)` -> dump every result (titles +
snippets + raw_content) straight into context. Ten advanced results can be
20k-40k tokens, re-paid on every follow-up turn.

Token Saver's answer, same as the PDF path: **search wide, inject narrow.**
1. Fetch rich results (raw_content where the provider gives it).
2. Passage-level retrieval against the query - reuses retrieve.py's hybrid
   keyword + (optional) semantic scorer, with neighbor sentences. Accuracy
   levers identical to the document path.
3. Cross-source dedup - the same fact echoed on six sites is paid once; the
   other URLs are kept as corroboration (good for grounding, free in tokens).
4. Token budget - greedily fill the best passages up to a ceiling; a source
   that can't fit keeps only title + url + one line.
5. Reversible (CCR-lite) - every full result is cached to .token_saver_cache/
   keyed by URL hash; the slice carries a manifest so the agent can pull a
   full body ONLY when a verification check fails (`search.py expand <url>`).

A coverage report (stderr) WARNs when query terms match nothing - the cue to
widen before trusting the answer. Output is compact, cited markdown.

Usage:
  export TAVILY_API_KEY=tvly-...
  python search.py query "GDPR data residency requirements 2026" \\
      --provider tavily --max-results 8 --budget 1200 --per-source 250 -o hits.md

  # inside an agent with a search CONNECTOR (e.g. Tavily MCP) instead of a key:
  # call the connector, then pipe its JSON response in via stdin
  <connector json> | python search.py query "..." --input - --budget 1200

  # offline / reproducible (no network, no key): feed a saved provider response
  python search.py query "..." --input fixtures/tavily.json --budget 1200

  # on-demand widen: print one source's full cached body
  python search.py expand https://example.com/article

  # token accounting only (prove the savings), no model call
  python search.py query "..." --input fixtures/tavily.json --count-only

Dependencies: requests (live providers). retrieve.py sibling (scoring).
sentence-transformers optional (semantic). trafilatura/bs4 optional (--fetch).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# Reuse the document path's accuracy scorers so search ranks the same way.
from retrieve import tokenize, keyword_scores, semantic_scores  # noqa: E402

CACHE_DIR = Path(os.environ.get("TOKEN_SAVER_CACHE", ".token_saver_cache"))
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
BOILER_RE = re.compile(
    r"cookie|subscribe|newsletter|share on|advertisement|related articles|"
    r"sign up|read more|terms of service|privacy policy|all rights reserved|"
    r"follow us|you may (also )?like", re.I)


def eprint(*a):
    print(*a, file=sys.stderr)


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Provider adapters -> normalized list of {title, url, content, raw_content, score}
# --------------------------------------------------------------------------- #
def _http_json(method, url, **kw):
    try:
        import requests
    except ImportError:
        eprint("Install requests: pip install requests"); sys.exit(2)
    r = requests.request(method, url, timeout=40, **kw)
    r.raise_for_status()
    return r.json()


def provider_tavily(query, max_results, depth):
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        eprint("No TAVILY_API_KEY found. Two ways to run:")
        eprint("  1) set a key: export TAVILY_API_KEY=tvly-...")
        eprint("  2) connector: if your agent has a search connector (e.g. Tavily MCP),")
        eprint("     call it, then pipe its JSON in:")
        eprint("     <connector-json> | python search.py query \"...\" --input -")
        sys.exit(2)
    data = _http_json("POST", "https://api.tavily.com/search", json={
        "api_key": key, "query": query, "search_depth": depth,
        "max_results": max_results, "include_raw_content": True,
        "include_answer": True,
    })
    return data.get("results", []), data.get("answer")


def provider_exa(query, max_results, depth):
    key = os.environ.get("EXA_API_KEY")
    if not key:
        eprint("Set EXA_API_KEY (or use --input)."); sys.exit(2)
    data = _http_json("POST", "https://api.exa.ai/search",
                      headers={"x-api-key": key},
                      json={"query": query, "numResults": max_results,
                            "contents": {"text": True}})
    out = []
    for r in data.get("results", []):
        out.append({"title": r.get("title"), "url": r.get("url"),
                    "content": (r.get("text") or "")[:500],
                    "raw_content": r.get("text"), "score": r.get("score")})
    return out, None


def provider_brave(query, max_results, depth):
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        eprint("Set BRAVE_API_KEY (or use --input)."); sys.exit(2)
    data = _http_json("GET", "https://api.search.brave.com/res/v1/web/search",
                      headers={"X-Subscription-Token": key,
                               "Accept": "application/json"},
                      params={"q": query, "count": max_results})
    out = []
    for r in data.get("web", {}).get("results", []):
        out.append({"title": r.get("title"), "url": r.get("url"),
                    "content": r.get("description"), "raw_content": None,
                    "score": None})  # brave: snippets only -> use --fetch
    return out, None


PROVIDERS = {"tavily": provider_tavily, "exa": provider_exa, "brave": provider_brave}


def normalize(results):
    norm = []
    for r in results:
        norm.append({
            "title": r.get("title") or "(untitled)",
            "url": r.get("url") or "",
            "content": r.get("content") or "",
            "raw_content": r.get("raw_content") or "",
            "score": r.get("score"),
        })
    return norm


def maybe_fetch_body(url):
    """Fallback for snippet-only providers: pull main content via web_extract path."""
    try:
        import trafilatura
        import requests
        html = requests.get(url, timeout=30,
                            headers={"User-Agent": "TokenSaver/1.0"}).text
        return trafilatura.extract(html, include_links=False,
                                   include_comments=False) or ""
    except Exception as e:
        eprint(f"  (fetch failed for {url}: {e})")
        return ""


# --------------------------------------------------------------------------- #
# Passage selection + dedup + budget
# --------------------------------------------------------------------------- #
def split_passages(text, window=3):
    sents = [s.strip() for s in SENT_RE.split(text) if s.strip()]
    # drop sentences that are mostly site chrome (cookie/subscribe/ads/etc.)
    sents = [s for s in sents if not BOILER_RE.search(s) or len(tokenize(s)) > 25]
    if not sents:
        return []
    return [" ".join(sents[i:i + window]) for i in range(0, len(sents), window)]


def shingles(text, n=4):
    toks = tokenize(text)
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def is_dup(sig, seen_sigs, thresh=0.6):
    for prev in seen_sigs:
        if not sig or not prev:
            continue
        j = len(sig & prev) / len(sig | prev)
        if j >= thresh:
            return True
    return False


def rank_passages(sources, query):
    """Score every (source_idx, passage) against the query using retrieve.py levers."""
    flat_text, owner = [], []
    for si, s in enumerate(sources):
        body = s["raw_content"] or s["content"]
        for p in split_passages(body):
            flat_text.append(p); owner.append(si)
    if not flat_text:
        return [], [], []
    kw, terms, missing = keyword_scores(flat_text, query)
    sem = semantic_scores(flat_text, query)
    scored = []
    for i, p in enumerate(flat_text):
        s = kw[i] + (5.0 * max(sem[i], 0) if sem is not None else 0)
        scored.append((s, owner[i], p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored, terms, missing


def build_slice(sources, query, budget, per_source, passages_per_source,
                top_k, answer, max_leads=5):
    scored, terms, missing = rank_passages(sources, query)
    used = est_tokens(query)
    seen_sigs, picked = [], {}  # si -> list[passage]
    src_tokens = {}
    corroborate = {}  # si -> count of dropped duplicates

    for score, si, passage in scored:
        if score <= 0:
            break
        if len(picked) >= top_k and si not in picked:
            continue
        if len(picked.get(si, [])) >= passages_per_source:
            continue
        sig = shingles(passage)
        if is_dup(sig, seen_sigs):
            corroborate[si] = corroborate.get(si, 0) + 1
            continue
        cost = est_tokens(passage)
        if used + cost > budget:
            continue
        if src_tokens.get(si, 0) + cost > per_source:
            continue
        picked.setdefault(si, []).append(passage)
        seen_sigs.append(sig)
        src_tokens[si] = src_tokens.get(si, 0) + cost
        used += cost

    # ---- cache every picked source's full body once (CCR-lite reversibility) ----
    CACHE_DIR.mkdir(exist_ok=True)
    for si in picked:
        cp = CACHE_DIR / f"{url_key(sources[si]['url'])}.txt"
        if not cp.exists():
            cp.write_text(sources[si]["raw_content"] or sources[si]["content"],
                          encoding="utf-8")
    parts = _rebuild_parts(sources, picked, corroborate, answer)
    leads = [s for i, s in enumerate(sources) if i not in picked]
    lead_lines = [f"- {s['title']} — {s['url']}" for s in leads[:max_leads]]

    def assemble(body_parts, lead_block):
        out = list(body_parts)
        if lead_block:
            out.append("\n## Unread leads (titles only — expand if needed)")
            out.extend(lead_block)
        return "\n".join(out).strip() + "\n"

    # Enforce the TOTAL token budget: drop leads first, then the lowest-ranked
    # passage, until the assembled slice fits (escalation in reverse).
    pick_order = [(si, p) for si, ps in picked.items() for p in ps]  # rank-ordered
    while True:
        slice_text = assemble(parts, lead_lines)
        if est_tokens(slice_text) <= budget or not (lead_lines or len(pick_order) > 1):
            break
        if lead_lines:
            lead_lines.pop()
            continue
        # remove the last (lowest-ranked) passage line block
        si_drop, p_drop = pick_order.pop()
        # rebuild parts without that one passage
        parts = _rebuild_parts(sources, picked := _drop_passage(picked, si_drop, p_drop),
                               corroborate, answer)

    slice_text = assemble(parts, lead_lines)
    report = {"terms": terms, "missing": missing,
              "picked_sources": sum(1 for v in picked.values() if v),
              "passages": sum(len(v) for v in picked.values()),
              "slice_tokens": est_tokens(slice_text)}
    return slice_text, report


def _drop_passage(picked, si, passage):
    if si in picked and passage in picked[si]:
        picked[si].remove(passage)
        if not picked[si]:
            del picked[si]
    return picked


def _rebuild_parts(sources, picked, corroborate, answer):
    parts = []
    if answer:
        parts.append(f"## Provider answer (verify against sources)\n{answer}\n")
    parts.append("## Sources (precise slices)")
    n = 0
    for si, passes in picked.items():
        if not passes:
            continue
        s = sources[si]; n += 1
        cache_path = CACHE_DIR / f"{url_key(s['url'])}.txt"
        corro = corroborate.get(si, 0)
        corro_tag = f" · corroborated by {corro} other source(s)" if corro else ""
        parts.append(f"\n### [{n}] {s['title']}\n{s['url']}{corro_tag}")
        for p in passes:
            parts.append(f"> {p}")
        parts.append(f"_(full body cached: {cache_path} — `search.py expand {s['url']}` to widen)_")
    return parts


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_query(args):
    if args.input:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text()
        raw = json.loads(text)
        results = raw.get("results", raw if isinstance(raw, list) else [])
        answer = raw.get("answer")
    else:
        fn = PROVIDERS.get(args.provider)
        if not fn:
            eprint(f"Unknown provider {args.provider}"); sys.exit(2)
        results, answer = fn(args.query, args.max_results, args.depth)

    sources = normalize(results)
    if args.fetch:
        for s in sources:
            if not (s["raw_content"] or "").strip():
                s["raw_content"] = maybe_fetch_body(s["url"])

    # naive baseline = everything a dump-it agent would inject
    naive = "\n".join((s["title"] + "\n" + s["url"] + "\n" +
                      (s["raw_content"] or s["content"])) for s in sources)
    naive_tok = est_tokens(naive) + est_tokens(args.query)

    slice_text, rep = build_slice(
        sources, args.query, args.budget, args.per_source,
        args.passages, args.max_results, answer if not args.no_answer else None,
        max_leads=args.max_leads)

    # Guard: never emit something larger than just handing back the results.
    # On snippet-only / already-tiny result sets the scaffolding can exceed the
    # raw dump — in that case emit the smaller of (compact passthrough, raw dump).
    passthrough = False
    if sources and rep["slice_tokens"] >= naive_tok:
        parts = []
        if answer and not args.no_answer:
            parts.append(f"## Provider answer (verify against sources)\n{answer}\n")
        parts.append("## Sources (already compact — passed through)")
        for i, s in enumerate(sources, 1):
            body = (s["raw_content"] or s["content"] or "").strip()
            parts.append(f"\n### [{i}] {s['title']}\n{s['url']}\n{body}")
        compact = "\n".join(parts).strip() + "\n"
        slice_text = compact if est_tokens(compact) <= naive_tok else naive
        rep["slice_tokens"] = est_tokens(slice_text)
        passthrough = True

    # ---- coverage / savings report (stderr) ----
    eprint("=" * 60)
    eprint(f"SEARCH COVERAGE (provider={args.provider if not args.input else 'file'}, "
           f"{len(sources)} results)")
    eprint(f"  query terms    : {', '.join(rep['terms']) or '(none)'}")
    eprint(f"  semantic match : {'on' if semantic_scores(['x'],'x') is not None else 'off (keyword only)'}")
    eprint(f"  sources used   : {rep['picked_sources']}  passages: {rep['passages']}")
    if rep["missing"]:
        eprint(f"  WARNING: query term(s) matched NOTHING: {', '.join(rep['missing'])}")
        eprint("  -> widen (raise --max-results / --budget) or rephrase before trusting.")
    eprint(f"  naive dump     : {naive_tok:,} tokens")
    if not sources:
        eprint("  (no results — nothing to slice; widen the query or check the provider)")
    elif passthrough:
        eprint(f"  token-saver slice: {rep['slice_tokens']:,} tokens "
               f"(results already small — passed through, no inflation)")
    elif rep["slice_tokens"] < naive_tok:
        eprint(f"  token-saver slice: {rep['slice_tokens']:,} tokens "
               f"({100*(1-rep['slice_tokens']/naive_tok):.1f}% smaller)")
    else:
        eprint(f"  token-saver slice: {rep['slice_tokens']:,} tokens "
               f"(results already small — no trim needed)")
    eprint("=" * 60)

    if args.count_only:
        return
    if args.out:
        Path(args.out).write_text(slice_text, encoding="utf-8")
        eprint(f"Wrote slice -> {args.out} (~{rep['slice_tokens']} tokens)")
    else:
        sys.stdout.write(slice_text)


def cmd_expand(args):
    path = CACHE_DIR / f"{url_key(args.url)}.txt"
    if not path.exists():
        eprint(f"No cached body for {args.url} (run a query first).")
        sys.exit(1)
    sys.stdout.write(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="search and emit a compact cited slice")
    q.add_argument("query")
    q.add_argument("--provider", default="tavily", choices=list(PROVIDERS))
    q.add_argument("--input", help="saved provider JSON response, or '-' to read JSON from stdin "
                                    "(use this to pipe results from a search connector / MCP)")
    q.add_argument("--max-results", type=int, default=8)
    q.add_argument("--depth", default="advanced", choices=["basic", "advanced"])
    q.add_argument("--budget", type=int, default=1200, help="total token ceiling for the slice")
    q.add_argument("--per-source", type=int, default=250, help="max tokens per source")
    q.add_argument("--passages", type=int, default=3, help="max passages per source")
    q.add_argument("--max-leads", type=int, default=5, help="unread-lead titles to list")
    q.add_argument("--fetch", action="store_true",
                   help="fetch main content for snippet-only providers (brave)")
    q.add_argument("--no-answer", action="store_true", help="drop the provider's own answer line")
    q.add_argument("--count-only", action="store_true", help="report tokens, write nothing")
    q.add_argument("-o", "--out", help="write slice to file (default: stdout)")
    q.set_defaults(func=cmd_query)

    e = sub.add_parser("expand", help="print one source's full cached body (on-demand widen)")
    e.add_argument("url")
    e.set_defaults(func=cmd_expand)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
