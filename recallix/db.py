"""Thin data-access layer. All calls use the user's JWT client, so RLS is always enforced.
`owner_id` is always supplied from the verified session (auth.user_id())."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from recallix import auth
from recallix.errors import AppError, get_logger

log = get_logger("db")


def _run(query):
    try:
        return query.execute().data
    except Exception as exc:
        log.error("db error: %s", type(exc).__name__)
        raise AppError("A database error occurred. Please try again.") from exc


def _t(name: str):
    return auth.client().table(name)


# ------------------------------------------------------------ profile & preferences
def get_profile() -> dict:
    rows = _run(_t("profiles").select("*").eq("id", auth.user_id()).limit(1))
    return rows[0] if rows else {"display_name": "", "email": st_email()}


def st_email() -> str:
    import streamlit as st

    return st.session_state.get("user", {}).get("email", "")


def update_display_name(name: str) -> None:
    _run(_t("profiles").update({"display_name": name.strip()[:80]}).eq("id", auth.user_id()))


DEFAULT_PREFS = {"language": "tanglish", "level": "beginner", "voice_lang": "en-IN",
                 "auto_speak": False, "history_limit": 10}


def get_prefs() -> dict:
    rows = _run(_t("user_preferences").select("*").eq("user_id", auth.user_id()).limit(1))
    if rows:
        return rows[0]
    _run(_t("user_preferences").insert({"user_id": auth.user_id()}))
    return dict(DEFAULT_PREFS)


def save_prefs(**fields) -> None:
    allowed = {k: v for k, v in fields.items() if k in DEFAULT_PREFS}
    _run(_t("user_preferences").update(allowed).eq("user_id", auth.user_id()))


# ------------------------------------------------------------ documents
def list_documents(limit: int = 100, favourites_only: bool = False) -> list[dict]:
    q = _t("documents").select("*").order("created_at", desc=True).limit(limit)
    if favourites_only:
        q = q.eq("is_favourite", True)
    return _run(q)


def get_document(doc_id: str) -> dict | None:
    rows = _run(_t("documents").select("*").eq("id", doc_id).limit(1))
    return rows[0] if rows else None


def find_document_by_hash(sha: str) -> dict | None:
    rows = _run(_t("documents").select("*").eq("sha256", sha).limit(1))
    return rows[0] if rows else None


def insert_document(row: dict) -> dict:
    row = {**row, "owner_id": auth.user_id()}
    return _run(_t("documents").insert(row))[0]


def update_document(doc_id: str, **fields) -> None:
    _run(_t("documents").update(fields).eq("id", doc_id))


def delete_document_row(doc_id: str) -> None:
    _run(_t("documents").delete().eq("id", doc_id))  # chunks cascade


def storage_used_bytes() -> int:
    rows = _run(_t("documents").select("size_bytes"))
    return sum(int(r["size_bytes"]) for r in rows)


def document_count() -> int:
    res = _t("documents").select("id", count="exact").limit(1).execute()
    return res.count or 0


# ------------------------------------------------------------ chunks
def replace_chunks(doc_id: str, chunks: list[dict]) -> None:
    uid = auth.user_id()
    _run(_t("document_chunks").delete().eq("document_id", doc_id))
    for i in range(0, len(chunks), 100):
        batch = [{**c, "document_id": doc_id, "owner_id": uid} for c in chunks[i:i + 100]]
        _run(_t("document_chunks").insert(batch))


def chunks_missing_embeddings(doc_id: str) -> list[dict]:
    return _run(_t("document_chunks").select("id,document_id,owner_id,chunk_index,page_number,section,content")
                .eq("document_id", doc_id).is_("embedding", "null").order("chunk_index").limit(5000))


def set_embeddings(rows: list[dict]) -> None:
    """rows = full chunk rows (incl. id) + 'embedding'. Upsert by primary key (needs the chunks_update policy)."""
    _run(_t("document_chunks").upsert(rows, on_conflict="id"))


def page_chunks(doc_id: str, page: int) -> list[dict]:
    return _run(_t("document_chunks").select("chunk_index,page_number,section,content")
                .eq("document_id", doc_id).eq("page_number", page).order("chunk_index"))


def all_chunks_sample(doc_id: str, max_chunks: int) -> list[dict]:
    rows = _run(_t("document_chunks").select("chunk_index,page_number,section,content")
                .eq("document_id", doc_id).order("chunk_index").limit(5000))
    if len(rows) <= max_chunks:
        return rows
    step = len(rows) / max_chunks
    return [rows[int(i * step)] for i in range(max_chunks)]


def match_chunks(doc_id: str, embedding: list[float], k: int = 6) -> list[dict]:
    try:
        res = auth.client().rpc("match_chunks", {"query_embedding": embedding, "p_document_id": doc_id,
                                                  "match_count": k}).execute()
        return res.data or []
    except Exception as exc:
        log.error("vector search failed: %s", type(exc).__name__)
        raise AppError("Document search is temporarily unavailable. Please retry.") from exc


def chunk_count(doc_id: str) -> tuple[int, int]:
    total = _t("document_chunks").select("id", count="exact").eq("document_id", doc_id).limit(1).execute().count or 0
    missing = (_t("document_chunks").select("id", count="exact").eq("document_id", doc_id)
               .is_("embedding", "null").limit(1).execute().count or 0)
    return total, missing


# ------------------------------------------------------------ conversations
def list_conversations(limit: int = 100) -> list[dict]:
    return _run(_t("conversations").select("*").order("updated_at", desc=True).limit(limit))


def get_conversation(conv_id: str) -> dict | None:
    rows = _run(_t("conversations").select("*").eq("id", conv_id).limit(1))
    return rows[0] if rows else None


def create_conversation(document_id: str | None, title: str) -> dict:
    return _run(_t("conversations").insert(
        {"owner_id": auth.user_id(), "document_id": document_id, "title": title[:120] or "New conversation"}))[0]


def rename_conversation(conv_id: str, title: str) -> None:
    _run(_t("conversations").update({"title": title.strip()[:120] or "Untitled"}).eq("id", conv_id))


def touch_conversation(conv_id: str) -> None:
    _run(_t("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", conv_id))


def delete_conversation(conv_id: str) -> None:
    _run(_t("conversations").delete().eq("id", conv_id))


def add_message(conv_id: str, role: str, content: str, language: str, sources: list | None = None) -> dict:
    return _run(_t("messages").insert({"conversation_id": conv_id, "owner_id": auth.user_id(), "role": role,
                                       "content": content[:60000], "language": language,
                                       "sources": sources or []}))[0]


def list_messages(conv_id: str, limit: int = 200) -> list[dict]:
    return _run(_t("messages").select("*").eq("conversation_id", conv_id).order("created_at").limit(limit))


def recent_messages(conv_id: str, n: int) -> list[dict]:
    rows = _run(_t("messages").select("role,content").eq("conversation_id", conv_id)
                .order("created_at", desc=True).limit(n))
    return list(reversed(rows))


def search_conversations(term: str) -> list[dict]:
    safe = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace(",", " ").replace("(", " ").replace(")", " ")
    msgs = _run(_t("messages").select("conversation_id").ilike("content", f"%{safe}%").limit(200))
    ids = {m["conversation_id"] for m in msgs}
    titles = _run(_t("conversations").select("*").ilike("title", f"%{safe}%").limit(100))
    found = {c["id"]: c for c in titles}
    if ids - set(found):
        for c in _run(_t("conversations").select("*").in_("id", list(ids - set(found))[:100])):
            found[c["id"]] = c
    return sorted(found.values(), key=lambda c: c["updated_at"], reverse=True)


# ------------------------------------------------------------ saved items
def save_answer(content: str, title: str, document_id: str | None) -> None:
    _run(_t("saved_answers").insert({"owner_id": auth.user_id(), "content": content[:60000],
                                     "title": title[:120], "document_id": document_id}))


def list_saved_answers() -> list[dict]:
    return _run(_t("saved_answers").select("*").order("created_at", desc=True).limit(200))


def delete_saved_answer(i: int) -> None:
    _run(_t("saved_answers").delete().eq("id", i))


def save_diagram(code: str, title: str) -> None:
    _run(_t("saved_diagrams").insert({"owner_id": auth.user_id(), "mermaid_code": code[:8000], "title": title[:120]}))


def list_saved_diagrams() -> list[dict]:
    return _run(_t("saved_diagrams").select("*").order("created_at", desc=True).limit(200))


def delete_saved_diagram(i: int) -> None:
    _run(_t("saved_diagrams").delete().eq("id", i))


# ------------------------------------------------------------ usage
def _since(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


def usage_units(kinds: list[str], since: timedelta) -> int:
    rows = _run(_t("usage_events").select("units").in_("kind", kinds).gte("created_at", _since(since)).limit(5000))
    return sum(int(r["units"]) for r in rows)


def record_usage(kind: str, units: int = 1) -> None:
    try:
        _t("usage_events").insert({"owner_id": auth.user_id(), "kind": kind, "units": units}).execute()
    except Exception as exc:  # never block the user because logging failed
        log.warning("usage record failed: %s", type(exc).__name__)
