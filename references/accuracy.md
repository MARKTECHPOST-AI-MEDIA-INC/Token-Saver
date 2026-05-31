# Accuracy: grounding, retrieval-that-doesn't-miss, verification

Aggressive trimming only fails when it drops the relevant part or when the model
fills the gap from priors. These three habits prevent both.

## The accuracy contract

1. **Ground and cite.** Every factual claim traces to a retrieved span: `[page 42]`,
   `row 1184`, a source URL. No pointer -> it doesn't go in the answer.
2. **Abstain or widen - never fill gaps from priors.** If the slice doesn't
   support an answer, say "not present in the retrieved material" or climb the
   escalation ladder. Do not answer from training knowledge.
3. **Verify before finalizing.** Re-read the answer against the slice; if a check
   fails, widen and redo.

## Retrieval that doesn't miss

Three levers, all built into `scripts/retrieve.py`:

- **Structural anchors.** Always include the outline/headings, defined terms,
  footnotes, and cross-references. Defeats the classic miss: a term defined on
  p.3 but used on p.80.
- **Hybrid matching.** Keyword always; semantic too when `sentence-transformers`
  is installed, so synonyms ("revenue recognition" vs "when we book sales")
  don't slip through. Keyword-only is the documented fallback.
- **Neighbor expansion.** Pull the pages/rows around each hit and follow explicit
  cross-references ("see section 4.2"). Answers rarely sit on exactly one page.

The coverage report is your miss detector: a **WARNING that a query term matched
nothing** means widen before trusting the answer.

## The escalation ladder (recap)

1. Targeted slice (cheapest) -> 2. Wider slice (more top-k / neighbors) ->
3. Full section read -> 4. Map-reduce the whole input (most thorough).

Stop at the first rung where verification passes. Cheap on easy docs, thorough
on hard ones.

## A verification pass you can run every time

- **Citation check:** is every claim tagged with a source location?
- **Coverage check:** did retrieval look where the inventory said the answer lives?
  Were all defined terms / cross-referenced sections pulled?
- **Completeness check:** for totals/counts/"every X", did you aggregate over
  everything (not a sample)?
- **Contradiction check:** does any cited span actually contradict the claim?
- **Gap check:** is anything asserted that has no citation? If so, remove it,
  abstain, or widen.

If any check fails: widen retrieval (next rung) and redo - don't paper over it.

## Honest limits

- Without `sentence-transformers`, pure-synonym matches can be missed; the coverage
  WARNING is the backstop - widen when it fires.
- Scanned pages have no text layer; OCR or flag them, never treat as empty.
- A static fetch can miss JS-rendered content; note it rather than inventing values.
