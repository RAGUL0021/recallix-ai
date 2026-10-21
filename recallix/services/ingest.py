"""Upload -> validate -> parse -> store -> chunk -> embed. Also delete / re-index."""
from __future__ import annotations

from typing import Callable

from recallix import auth, db, llm, quota, storage
from recallix.chunking import chunk_units
from recallix.config import get_settings
from recallix.errors import AppError, QuotaExceeded, ValidationFailed, get_logger
from recallix.parsers import parse_document
from recallix.security import (EXT_MAP, extension_of, sanitize_filename, sha256_of, storage_path_for,
                               validate_content)

log = get_logger("ingest")
Progress = Callable[[float, str], None]


def _noop(_p: float, _m: str) -> None:
    pass

def ingest_upload(filename: str, data: bytes, progress: Progress = _noop) -> dict:
    s = get_settings()
    uid = auth.user_id()
    safe_name = sanitize_filename(filename)
    ext = extension_of(safe_name)
    progress(0.05, "Checking file…")
    file_type = validate_content(ext, data)
    quota.check_upload_quota(len(data))

    sha = sha256_of(data)
    existing = db.find_document_by_hash(sha)
    if existing:
        raise ValidationFailed(
            f"You already uploaded this file as “{existing.get('original_name') or existing.get('filename')}”.")

    progress(0.15, "Reading document…")
    parsed = parse_document(data, file_type, max_ocr_pages=s.max_ocr_pages, max_table_rows=s.max_table_rows)

    progress(0.3, "Saving file privately…")
    path = storage_path_for(uid, safe_name)
    storage.upload(path, data, EXT_MAP[ext][1])
    try:
        status = "needs_ocr" if parsed.needs_ocr else "processing"
        row = db.insert_document({
            "filename": safe_name,           # NOT NULL column
            "original_name": safe_name,      # dashboard.py idhai dhaan padikkudhu
            "file_type": file_type, "mime_type": EXT_MAP[ext][1],
            "size_bytes": len(data), "storage_path": path, "sha256": sha,
            "status": status, "status_detail": " ".join(parsed.notes), "page_count": len(parsed.units),
        })
    except Exception:
        storage.remove(path)  # don't leave orphaned files
        raise
    db.record_usage("upload", 1)
    _store_chunks_and_embed(row["id"], parsed, progress, keep_status=parsed.needs_ocr)
    return db.get_document(row["id"]) or row


def _store_chunks_and_embed(doc_id: str, parsed, progress: Progress, keep_status: bool = False) -> None:
    chunks = chunk_units(parsed.units)
    if not chunks:
        db.update_document(doc_id, status="needs_ocr" if parsed.needs_ocr else "failed",
                           status_detail="No readable text was found in this file." + (
                               " You can run OCR to extract text from scans." if parsed.needs_ocr else ""))
        return
    progress(0.45, f"Preparing {len(chunks)} text chunks…")
    db.replace_chunks(doc_id, chunks)
    try:
        embed_pending(doc_id, progress)
        if not keep_status:
            db.update_document(doc_id, status="ready")
    except QuotaExceeded as exc:
        db.update_document(doc_id, status="failed", status_detail=exc.user_message + " Use “Retry indexing” later.")
    except AppError as exc:
        db.update_document(doc_id, status="failed", status_detail=exc.user_message + " Use “Retry indexing”.")


def embed_pending(doc_id: str, progress: Progress = _noop) -> int:
    """Embed every chunk that has no embedding yet. Safe to call repeatedly (retry)."""
    pending = db.chunks_missing_embeddings(doc_id)
    if not pending:
        return 0
    quota.check_embed_quota(len(pending))
    done = 0
    for i in range(0, len(pending), 64):
        batch = pending[i:i + 64]
        vectors = llm.embed([c["content"] for c in batch])
        db.set_embeddings([{**c, "embedding": v} for c, v in zip(batch, vectors)])
        done += len(batch)
        progress(0.5 + 0.5 * done / len(pending), f"Indexing {done}/{len(pending)} chunks…")
    db.record_usage("embed_chunks", done)
    return done


def retry_indexing(doc_id: str, progress: Progress = _noop) -> None:
    embed_pending(doc_id, progress)
    db.update_document(doc_id, status="ready", status_detail="")


def run_ocr(doc_id: str, progress: Progress = _noop) -> None:
    doc = db.get_document(doc_id)
    if not doc:
        raise AppError("Document not found.")
    s = get_settings()
    progress(0.05, "Downloading file…")
    data = storage.download(doc["storage_path"])
    progress(0.15, "Running OCR (this can take a while)…")
    parsed = parse_document(data, doc["file_type"], ocr=True, max_ocr_pages=s.max_ocr_pages)
    db.update_document(doc_id, status_detail=" ".join(parsed.notes), page_count=len(parsed.units))
    if parsed.total_chars < 25:
        db.update_document(doc_id, status="needs_ocr",
                           status_detail="OCR found no readable text. " + " ".join(parsed.notes))
        raise AppError("OCR could not find readable text in this file.")
    _store_chunks_and_embed(doc_id, parsed, progress)


def delete_document(doc_id: str) -> None:
    """Removes the stored file, the row, and (by cascade) all chunks and embeddings."""
    doc = db.get_document(doc_id)
    if not doc:
        return
    storage.remove(doc["storage_path"])
    db.delete_document_row(doc_id)
