"""Split page/slide units into overlapping chunks that keep their page reference."""
from __future__ import annotations


def split_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if cut > size * 0.6:  # prefer a natural boundary, but not too early
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def chunk_units(units, size: int = 1200, overlap: int = 200) -> list[dict]:
    """`units` are parsers.Unit objects. Returns dicts ready for the document_chunks table."""
    chunks: list[dict] = []
    for unit in units:
        for piece in split_text(unit.text, size, overlap):
            chunks.append(
                {"chunk_index": len(chunks), "page_number": unit.number, "section": unit.label, "content": piece}
            )
    return chunks
