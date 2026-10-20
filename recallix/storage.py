"""Private Supabase Storage access (policies restrict each user to their own folder)."""
from __future__ import annotations

from recallix import auth
from recallix.errors import AppError, get_logger

log = get_logger("storage")
BUCKET = "document"


def upload(path: str, data: bytes, mime: str) -> None:
    try:
        auth.client().storage.from_(BUCKET).upload(path, data, {"content-type": mime, "upsert": "false"})
    except Exception as exc:
        log.error("storage upload failed: %s", type(exc).__name__)
        raise AppError("Could not save the file to storage. Please try again.") from exc

def download(path: str) -> bytes:
    try:
        return auth.client().storage.from_(BUCKET).download(path)
    except Exception:
        log.exception("Storage download failed for path: %s", path)
        raise AppError(
            "Could not load the file from storage. Check server logs."
        )

def remove(path: str) -> None:
    try:
        auth.client().storage.from_(BUCKET).remove([path])
    except Exception as exc:
        log.error("storage delete failed: %s", type(exc).__name__)
        raise AppError("Could not delete the stored file. Please try again.") from exc
