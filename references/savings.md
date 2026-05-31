# Maximizing token savings (the savings ladder)

Apply in roughly this order. The first lever does most of the work; caching is
the biggest multi-turn multiplier.

## 1. Bulk in code, not context (biggest lever)

The whole skill. A 200-page PDF (~150k tokens) in context is re-sent on every
turn; the same questions answered from a small retrieved slice are paid once.
Keep raw data in files and code; surface only the distilled result.

## 2. Cache the stable context

Put anything that persists across turns - system prompt, the skill instructions,
a long reference doc - behind prompt caching. Cached tokens are billed at a
fraction of fresh input tokens, so on multi-turn work this often dominates the
bill. It **stacks with** precise retrieval; it doesn't replace it.

Anthropic API example - mark the stable block with `cache_control`:

```python
client.messages.create(
    model="claude-3-5-sonnet-latest",
    max_tokens=400,
    system=[
        {"type": "text", "text": SKILL_AND_REFERENCE_TEXT,
         "cache_control": {"type": "ephemeral"}},   # cached across turns
    ],
    messages=[{"role": "user", "content": question}],
)
```

Put the large, unchanging material first; keep the per-turn question outside the
cached block. Reuse the same prefix every turn to hit the cache.

## 3. Strip and compress

- Drop boilerplate, whitespace, nav/footers, repeated headers.
- Tables -> CSV (compact and unambiguous), not prose dumps.
- Ask for terse, structured output; don't restate the input back to the user.

## 4. Reuse artifacts

Extract once to disk (`slice.txt`, `tables/`, `chunks/`); on later turns read only the
slice you need. Never re-extract or re-paste the same block.

## 5. Offload to a separate context

Run heavy extraction/summarization in a sub-agent or separate thread whose tokens
don't pollute the main conversation, and return only its small result (where the
platform supports it).

## 6. Budget

Set a per-task token ceiling. If a candidate slice would blow it, **retrieve
harder** (tighter query, fewer pages) rather than dumping more in. A budget keeps
"just in case" context from creeping back.

## Why savings compound

| Turns | Naive (whole doc each turn) | Token Saver (slice + cached prefix) |
| --- | --- | --- |
| 1 | full doc | small slice |
| 5 | 5x full doc | 5 small slices, prefix cached |
| 20 | 20x full doc | 20 small slices, prefix cached |

The naive line grows linearly with every follow-up; the skill line stays flat
and cheap. Use `eval/measure_tokens.py` to see the gap on your own document.
