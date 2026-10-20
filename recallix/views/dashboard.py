"""Dashboard: usage, upload, recent documents and conversations."""
from __future__ import annotations

import streamlit as st

from recallix import db, quota
from recallix.config import get_settings
from recallix.errors import AppError
from recallix.parsers import ocr_available
from recallix.security import ALLOWED_EXTENSIONS
from recallix.services import ingest
from recallix.ui.nav import go, show_flash, top_bar


def upload_widget() -> None:
    s = get_settings()
    nonce = st.session_state.setdefault("upload_nonce", 0)
    files = st.file_uploader(
        f"Drag and drop files here (max {s.max_upload_mb} MB each)",
        type=ALLOWED_EXTENSIONS, accept_multiple_files=True, key=f"uploader_{nonce}",
        help="PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), CSV, text, Markdown, RTF, source code, PNG/JPEG.")
    if not files:
        return
    for f in files:
        bar = st.progress(0.0, text=f"{f.name}: starting…")
        try:
            doc = ingest.ingest_upload(f.name, f.getvalue(), lambda p, m, n=f.name: bar.progress(min(p, 1.0), text=f"{n}: {m}"))
            bar.empty()
            if doc["status"] == "ready":
                st.success(f"“{doc['original_name']}” is ready.")
            else:
                st.warning(f"“{doc['original_name']}” was saved, but: {doc['status_detail'] or doc['status']}")
        except AppError as exc:
            bar.empty()
            st.error(f"{f.name}: {exc.user_message}")
    if st.button("Done — clear upload list", key="clear_up"):
        st.session_state["upload_nonce"] = nonce + 1
        st.rerun()


def document_card(doc: dict, key: str) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([4, 3])
        with c1:
            st.markdown(f"**{'⭐ ' if doc['is_favourite'] else ''}{doc['original_name']}**")
            st.markdown(
                f"<span class='rx-pill rx-{doc['status']}'>{doc['status'].replace('_', ' ')}</span> "
                f"<span class='rx-muted'>{doc['file_type'].upper()} · {doc['size_bytes'] / 1024:,.0f} KB · "
                f"{doc['page_count']} part(s) · {doc['created_at'][:10]}</span>", unsafe_allow_html=True)
            if doc["status_detail"]:
                st.caption(doc["status_detail"])
        with c2:
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("Open", key=f"o_{key}", type="primary", use_container_width=True):
                go("workspace", doc_id=doc["id"], conv_id=None, cur_unit=1)
            if b2.button("⭐" if not doc["is_favourite"] else "★", key=f"f_{key}", use_container_width=True,
                         help="Save / unsave"):
                db.update_document(doc["id"], is_favourite=not doc["is_favourite"])
                st.rerun()
            if b3.button("✏️", key=f"r_{key}", use_container_width=True, help="Rename"):
                st.session_state[f"renaming_{key}"] = True
            if b4.button("🗑", key=f"d_{key}", use_container_width=True, help="Delete"):
                st.session_state[f"confirm_del_{key}"] = True
        if st.session_state.get(f"renaming_{key}"):
            new = st.text_input("New name", value=doc["original_name"], key=f"rn_{key}")
            if st.button("Save name", key=f"rns_{key}"):
                from recallix.security import sanitize_filename

                db.update_document(doc["id"], original_name=sanitize_filename(new))
                st.session_state.pop(f"renaming_{key}")
                st.rerun()
        if st.session_state.get(f"confirm_del_{key}"):
            st.warning("Delete this document, its extracted text and its search index? This cannot be undone.")
            y, n = st.columns(2)
            if y.button("Yes, delete", key=f"dy_{key}", type="primary"):
                try:
                    ingest.delete_document(doc["id"])
                except AppError as exc:
                    st.error(exc.user_message)
                st.session_state.pop(f"confirm_del_{key}", None)
                st.rerun()
            if n.button("Cancel", key=f"dn_{key}"):
                st.session_state.pop(f"confirm_del_{key}")
                st.rerun()
        if doc["status"] == "failed":
            if st.button("Retry indexing", key=f"ri_{key}"):
                try:
                    with st.spinner("Indexing…"):
                        ingest.retry_indexing(doc["id"])
                    st.rerun()
                except AppError as exc:
                    st.error(exc.user_message)
        if doc["status"] == "needs_ocr":
            if ocr_available():
                st.caption("No extractable text found. OCR can read scans, but may contain recognition errors.")
                if st.button("Run OCR", key=f"ocr_{key}"):
                    bar = st.progress(0.0, text="Starting OCR…")
                    try:
                        ingest.run_ocr(doc["id"], lambda p, m: bar.progress(min(p, 1.0), text=m))
                        st.rerun()
                    except AppError as exc:
                        st.error(exc.user_message)
            else:
                st.caption("This file has no extractable text and OCR is not installed on this server.")


def render() -> None:
    top_bar()
    show_flash()
    st.title("Your learning desk")
    try:
        u = quota.snapshot()
    except AppError as exc:
        st.error(exc.user_message)
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("AI requests today", f"{u['ai_today']} / {u['ai_limit']}")
    m2.metric("Storage", f"{u['storage_mb']:.1f} / {u['storage_limit_mb']} MB")
    m3.metric("Documents", f"{u['docs']} / {u['docs_limit']}")

    with st.expander("Upload documents", expanded=u["docs"] == 0):
        upload_widget()

    st.subheader("Recent documents")
    docs = db.list_documents(limit=8)
    if not docs:
        st.info("No documents yet. Upload a PDF, slide deck or code file above to begin.")
    for d in docs:
        document_card(d, d["id"][:8])
    if st.button("See all saved documents", key="all_docs"):
        go("saved")

    st.subheader("Recent conversations")
    convs = db.list_conversations(limit=5)
    if not convs:
        st.caption("Your conversations will appear here.")
    for c in convs:
        a, b = st.columns([5, 1])
        a.markdown(f"💬 **{c['title']}**  \n<span class='rx-muted'>{c['updated_at'][:16].replace('T', ' ')}</span>",
                   unsafe_allow_html=True)
        if b.button("Open", key=f"rc_{c['id'][:8]}"):
            go("workspace", doc_id=c["document_id"], conv_id=c["id"], cur_unit=1)
