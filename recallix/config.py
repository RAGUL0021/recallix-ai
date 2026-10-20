"""Central configuration. Values come from environment variables, a .env file,
or Streamlit secrets (in that order). Secrets are never hard-coded."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    try:  # st.secrets raises if no secrets file exists
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    gemini_api_key: str
    gemini_model: str
    embed_model: str
    app_url: str
    max_upload_mb: int
    max_storage_mb: int
    max_documents: int
    daily_ai_limit: int
    hourly_ai_limit: int
    daily_embed_chunk_limit: int
    max_ocr_pages: int
    max_table_rows: int

    def missing(self) -> list[str]:
        required = {
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_ANON_KEY": self.supabase_anon_key,
            "GEMINI_API_KEY": self.gemini_api_key,
        }
        return [k for k, v in required.items() if not v]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        supabase_url=_get("SUPABASE_URL", "") or "",
        supabase_anon_key=_get("SUPABASE_ANON_KEY", "") or "",
        gemini_api_key=_get("GEMINI_API_KEY", "") or "",
        # Model names change over time. Check https://ai.google.dev/gemini-api/docs/models
        gemini_model=_get("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash",
        embed_model=_get("GEMINI_EMBED_MODEL", "gemini-embedding-001") or "gemini-embedding-001",
        app_url=(_get("APP_URL", "http://localhost:8501") or "").rstrip("/"),
        max_upload_mb=_int("MAX_UPLOAD_MB", 25),
        max_storage_mb=_int("MAX_STORAGE_MB", 200),
        max_documents=_int("MAX_DOCUMENTS", 50),
        daily_ai_limit=_int("DAILY_AI_LIMIT", 60),
        hourly_ai_limit=_int("HOURLY_AI_LIMIT", 25),
        daily_embed_chunk_limit=_int("DAILY_EMBED_CHUNK_LIMIT", 4000),
        max_ocr_pages=_int("MAX_OCR_PAGES", 40),
        max_table_rows=_int("MAX_TABLE_ROWS", 50000),
    )


EMBED_DIM = 768  # must match extensions.vector(768) in the SQL migration
