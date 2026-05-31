# PDFs and long documents

Apply the six-step workflow from SKILL.md. PDF-specific tactics below.

## 1. Inventory cheaply

Get structure before any content:

```bash
python scripts/pdf_inspect.py info report.pdf
```

This prints page count, the outline/bookmarks, per-page text length, and flags
**low-text (likely scanned) pages**. The outline tells you where the answer
probably lives, so retrieval doesn't miss; the scanned flag stops you from
reading "no extractable text" as "nothing relevant here."

## 2. Retrieve precisely

Prefer `retrieve.py` over a raw search - it adds structural anchors, hybrid
matching, neighbor expansion, and a coverage report in one pass:

```bash
python scripts/retrieve.py report.pdf --query "indemnification cap" \
    --top-k 5 --neighbors 1 --anchors --follow-xrefs -o slice.txt
```

For a quick literal lookup with page numbers + neighbor suggestions:

```bash
python scripts/pdf_inspect.py search report.pdf "clause 7.2" --neighbors 1
```

**Why anchors matter for PDFs:** definitions, footnotes, and "as defined in
Section 2" live far from where a term is used. Always include the outline and
follow cross-references so the defining page comes along with the using page.

## 3. Extract what you need

Pull only the relevant page range; convert tables instead of trusting a dump:

```bash
python scripts/pdf_inspect.py text report.pdf --pages 12-14 -o slice.txt
python scripts/pdf_inspect.py tables report.pdf --pages 12-14 -o tables/
```

A mangled inline table is an accuracy risk - extract to CSV and read the CSV.

## 4. Whole-document tasks (map-reduce)

When a task genuinely spans the entire document (e.g. "summarize every section"),
chunk to disk and process one chunk at a time - the full text never sits in
context at once:

```bash
python scripts/pdf_inspect.py map report.pdf --chunk 5 -o chunks/
```

Summarize each chunk file to a short note on disk, then combine the notes.

## Scanned / image PDFs

If `info` flags low-text pages, the text layer is missing. OCR them first (e.g.
`ocrmypdf in.pdf out.pdf`) or treat those pages as images - do not assume they
contain nothing.

## Accuracy checklist (before answering)

- Every claim cites a `[page N]`.
- Defined terms / cross-referenced sections were pulled, not just the hit page.
- The coverage report showed no unmatched query terms (else widen first).
- Numbers came from extracted tables, not a mangled text dump.
