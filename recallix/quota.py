"""Per-user rate limits and quotas for public deployments."""
from __future__ import annotations

import time
from datetime import timedelta

import streamlit as st

from recallix import db
from recallix.config import get_settings
from recallix.errors import QuotaExceeded

AI_KINDS = ["ai_chat", "ai_diagram", "ai_transcribe"]
MIN_SECONDS_BETWEEN_CALLS = 2.0


def check_ai_quota() -> None:
    s = get_settings()
    now = time.time()
    last = st.session_state.get("_last_ai_call", 0.0)
    if now - last < MIN_SECONDS_BETWEEN_CALLS:
        raise QuotaExceeded("You're going a little fast. Wait a couple of seconds and try again.")
    if db.usage_units(AI_KINDS, timedelta(hours=1)) >= s.hourly_ai_limit:
        raise QuotaExceeded(f"Hourly limit reached ({s.hourly_ai_limit} AI requests). Please try again later.")
    if db.usage_units(AI_KINDS, timedelta(days=1)) >= s.daily_ai_limit:
        raise QuotaExceeded(f"Daily free limit reached ({s.daily_ai_limit} AI requests). It resets within 24 hours.")
    st.session_state["_last_ai_call"] = now


def check_embed_quota(chunks: int) -> None:
    s = get_settings()
    used = db.usage_units(["embed_chunks"], timedelta(days=1))
    if used + chunks > s.daily_embed_chunk_limit:
        raise QuotaExceeded("Today's document-indexing limit is reached. Try uploading smaller files tomorrow.")


def check_upload_quota(new_bytes: int) -> None:
    s = get_settings()
    if new_bytes > s.max_upload_mb * 1024 * 1024:
        raise QuotaExceeded(f"File is larger than the {s.max_upload_mb} MB upload limit.")
    if db.document_count() >= s.max_documents:
        raise QuotaExceeded(f"You have reached the limit of {s.max_documents} documents. Delete one to continue.")
    if db.storage_used_bytes() + new_bytes > s.max_storage_mb * 1024 * 1024:
        raise QuotaExceeded(f"This upload would exceed your {s.max_storage_mb} MB storage limit.")


def snapshot() -> dict:
    s = get_settings()
    return {
        "ai_today": db.usage_units(AI_KINDS, timedelta(days=1)), "ai_limit": s.daily_ai_limit,
        "storage_mb": db.storage_used_bytes() / 1024 / 1024, "storage_limit_mb": s.max_storage_mb,
        "docs": db.document_count(), "docs_limit": s.max_documents,
    }
