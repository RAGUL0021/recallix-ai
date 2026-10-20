"""Retrieval for large documents: only relevant chunks are sent to Gemini."""
from __future__ import annotations

from recallix import db, llm
from recallix.security import escape_delimiters

MAX_CONTEXT_CHARS = 24000
MODE_SMART, MODE_PAGE, MODE_DOC = "smart", "page", "document"


def _label(doc: dict, unit_label: str, row: dict) -> str:
    sec = row.get("section") or f"{unit_label} {row['page_number']}"
    return f"{doc['original_name']} — {sec}"


def unit_label_for(file_type: str) -> str:
    return {"pdf": "Page", "pptx": "Slide", "docx": "Section", "image": "Image"}.get(file_type, "Block")


def build_context(doc: dict, question: str, current_unit: int, mode: str) -> tuple[str, list[dict]]:
    """Returns (context text with [S#] labels, sources list). Sources are computed by the app, never by the model."""
    ul = unit_label_for(doc["file_type"])
    rows: list[dict] = []
    seen: set[int] = set()

    def add(items):
        for r in items:
            key = hash(r["content"])
            if key not in seen:
                seen.add(key)
                rows.append(r)

    span = 5 if doc["file_type"] in ("code", "text", "markdown", "rtf") else 1  # 400 lines == 5 line-blocks
    if mode == MODE_PAGE:
        for p in range(current_unit, current_unit + span):
            add(db.page_chunks(doc["id"], p))
    elif mode == MODE_DOC:
        add(db.all_chunks_sample(doc["id"], 28))
    else:
        add(db.page_chunks(doc["id"], current_unit)[:2])  # what the learner is looking at
        try:
            vec = llm.embed([question], query=True)[0]
            add(db.match_chunks(doc["id"], vec, 6))
        except Exception:
            # Embeddings unavailable: fall back to the current page + evenly spaced samples.
            add(db.all_chunks_sample(doc["id"], 8))

    parts, sources, total = [], [], 0
    for i, r in enumerate(rows, start=1):
        text = escape_delimiters(r["content"])
        if total + len(text) > MAX_CONTEXT_CHARS:
            break
        label = _label(doc, ul, r)
        parts.append(f"[S{i}] ({label})\n{text}")
        sources.append({"id": f"S{i}", "label": label, "page": r["page_number"]})
        total += len(text)
    return "\n\n".join(parts), sources
