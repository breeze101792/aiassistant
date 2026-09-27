# ADR-0014 — Keep markdown memory and the SQLite cache

**Status:** accepted · **Date:** 2026-09-26

## Decision

Keep the existing storage: markdown files as the system of record, SQLite as a
rebuildable derived index. Change the **writer**, not the format.

## Why

The markdown format is human-readable, greppable, and diffable, which matters for
a personal assistant the user may want to read and edit by hand. The SQLite file
is explicitly a cache — `embeddings.py:156` can rebuild it from the markdown
(`rebuild_index`), which makes deleting it safe.

There is no scale problem: it is one user's transcript on one machine.

The real defects are elsewhere and are fixed without a format change:

| Defect | Evidence | Fix |
| --- | --- | --- |
| Two writers for the same turn | `Responder.save_turn` (`respond.py:27`) and `MemoryManager.save_turn` (`memory.py:25`) are near-duplicates; only one is called | Collapse into one module |
| Embedding search scans every row in Python | `embeddings.py:196` loads the whole table, then computes cosine per row | Left as-is; noted as a v2 candidate |
| Embedding calls block the loop | `embeddings.py:65` calls a synchronous provider from async code | Run off-loop or from cache (REQ-MEM-006) |

## Rejected

| Alternative | Why rejected |
| --- | --- |
| Move to SQLite for everything | Loses human readability for no scale benefit |
| A vector database | Operationally heavy for a personal transcript; the linear scan is acceptable at this size |
| JSONL transcripts | Less readable and less diffable than markdown; no real gain |
| New format with a migration | Migration risk and work for zero user-visible benefit |

## Consequences

- The format is documented as **frozen** in
  [data-model.md](../data-model.md), so future changes are deliberate.
- Changing the embedding model requires a rebuild, because a dimension mismatch
  causes rows to be skipped silently (`embeddings.py:202`). Documented, and the
  rebuild path exists.
- Semantic recall stays behind a flag (`memory.semantic`), off by default, while
  basic persistence is on the must-have path.
