"""File validation and sanitisation helpers. Everything here is pure Python (easy to unit test)."""
from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
import zipfile

from recallix.errors import ValidationFailed

# extension -> (file_type, mime)
CODE_EXTS = {
    "py", "java", "c", "h", "cpp", "hpp", "cc", "js", "jsx", "ts", "tsx",
    "html", "css", "json", "xml", "yaml", "yml", "sql", "sh", "go", "rs", "php", "rb", "cs", "kt",
}
EXT_MAP: dict[str, tuple[str, str]] = {
    "pdf": ("pdf", "application/pdf"),
    "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": ("csv", "text/csv"),
    "txt": ("text", "text/plain"),
    "md": ("markdown", "text/markdown"),
    "rtf": ("rtf", "application/rtf"),
    "png": ("image", "image/png"),
    "jpg": ("image", "image/jpeg"),
    "jpeg": ("image", "image/jpeg"),
    **{e: ("code", "text/plain") for e in CODE_EXTS},
}
LEGACY_UNSUPPORTED = {"doc", "ppt", "xls"}
ALLOWED_EXTENSIONS = sorted(EXT_MAP)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ \-()]")


def sanitize_filename(name: str) -> str:
    """Strip directories and unsafe characters. Result is for DISPLAY only; storage uses a UUID."""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = _SAFE_NAME.sub("_", base).lstrip(".")
    base = re.sub(r"\.{2,}", ".", base)
    if not base:
        raise ValidationFailed("The file name is empty or invalid.")
    if len(base) > 150:
        stem, _, ext = base.rpartition(".")
        base = (stem[:140] + "." + ext) if stem else base[:150]
    return base


def extension_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def storage_path_for(user_id: str, original_name: str) -> str:
    """<user_id>/<random uuid>.<ext>  — the first folder must be the owner's id (storage RLS)."""
    ext = extension_of(original_name)
    return f"{user_id}/{uuid.uuid4().hex}.{ext}" if ext else f"{user_id}/{uuid.uuid4().hex}"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_zip_container(data: bytes, required_prefix: str) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationFailed("This file is corrupted or is not a valid Office document.") from exc
    infos = zf.infolist()
    total = sum(i.file_size for i in infos)
    if total > 400 * 1024 * 1024 or len(infos) > 20000:
        raise ValidationFailed("This file expands to an unsafe size and was rejected.")
    names = {i.filename for i in infos}
    if "[Content_Types].xml" not in names or not any(n.startswith(required_prefix) for n in names):
        raise ValidationFailed("The file content does not match its extension.")
    if any(n.startswith("/") or ".." in n.split("/") for n in names):
        raise ValidationFailed("The file contains unsafe paths and was rejected.")
    if "word/vbaProject.bin" in names or "ppt/vbaProject.bin" in names or "xl/vbaProject.bin" in names:
        raise ValidationFailed("Documents containing macros are not accepted.")


def validate_content(ext: str, data: bytes) -> str:
    """Server-side check that the bytes really match the claimed type. Returns file_type."""
    if ext in LEGACY_UNSUPPORTED:
        raise ValidationFailed(
            f".{ext} is an old binary Office format that cannot be processed safely here. "
            f"Please save it as .{ext}x and upload that."
        )
    if ext not in EXT_MAP:
        raise ValidationFailed(f"Unsupported file type '.{ext}'. Supported: {', '.join(ALLOWED_EXTENSIONS)}.")
    if not data:
        raise ValidationFailed("The file is empty.")
    file_type = EXT_MAP[ext][0]

    if file_type == "pdf":
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            raise ValidationFailed("The file content is not a PDF.")
    elif file_type in ("docx", "pptx", "xlsx"):
        prefix = {"docx": "word/", "pptx": "ppt/", "xlsx": "xl/"}[file_type]
        _check_zip_container(data, prefix)
    elif file_type == "image":
        sig_ok = data.startswith(b"\x89PNG\r\n\x1a\n") if ext == "png" else data.startswith(b"\xff\xd8\xff")
        if not sig_ok:
            raise ValidationFailed("The file content does not match its image extension.")
    else:  # text-like
        if b"\x00" in data[:8192]:
            raise ValidationFailed("This looks like a binary file, not text or source code.")
    return file_type


def escape_delimiters(text: str) -> str:
    """Neutralise our prompt delimiters inside untrusted document text."""
    return re.sub(r"<\s*/?\s*(document_context|selected_text|system|instructions?)[^>]*>", "[tag removed]", text, flags=re.I)


def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Use at least 8 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Include at least one letter and one number."
    return None


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def validate_email(email: str) -> bool:
    return bool(_EMAIL.match(email or "")) and len(email) <= 254
