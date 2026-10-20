"""Document viewers. PDFs are rendered page-by-page as images with PyMuPDF (only the pages on screen are
rendered, so long books never load fully into memory). Nothing uploaded is ever executed."""
from __future__ import annotations

import html

import streamlit as st
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename

from recallix import parsers
from recallix.config import get_settings

CODE_PAGE_LINES = 400
ZOOMS = [0.6, 0.8, 1.0, 1.25, 1.5, 2.0]


def _cache(doc_id: str) -> dict:
    c = st.session_state.get("_view")
    if not c or c["doc_id"] != doc_id:
        c = {"doc_id": doc_id, "pages": {}, "parsed": None, "text": None}
        st.session_state["_view"] = c
    return c


def pdf_page_png(doc: dict, data: bytes, page: int, scale: float) -> bytes:
    c = _cache(doc["id"])
    key = (page, scale)
    if key not in c["pages"]:
        if len(c["pages"]) > 24:  # keep memory bounded
            c["pages"].pop(next(iter(c["pages"])))
        c["pages"][key] = parsers.render_pdf_page(data, page, scale)
    return c["pages"][key]


def get_parsed(doc: dict, data: bytes):
    c = _cache(doc["id"])
    if c["parsed"] is None:
        c["parsed"] = parsers.parse_document(data, doc["file_type"], max_table_rows=get_settings().max_table_rows)
    return c["parsed"]


def get_text(doc: dict, data: bytes) -> str:
    c = _cache(doc["id"])
    if c["text"] is None:
        c["text"] = parsers.decode_text(data)
    return c["text"]


# ------------------------------------------------------------------ PDF
def render_pdf(doc: dict, data: bytes, cur: int, total: int) -> int:
    zoom_i = st.session_state.setdefault("zoom_i", 2)
    fit = st.session_state.setdefault("fit", True)
    shown = st.session_state.setdefault("pages_shown", 1)

    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1.4, 1, 1, 1.4])
    if c1.button("◀ Prev", key="pv", disabled=cur <= 1, use_container_width=True):
        cur -= 1
    if c2.button("Next ▶", key="nx", disabled=cur >= total, use_container_width=True):
        cur += 1
    new = c3.number_input("Page", 1, total, cur, key=f"pgin_{cur}", label_visibility="collapsed")
    if new != cur:
        cur = int(new)
    c3.caption(f"of {total}")
    if c4.button("➖ Zoom", key="zo", use_container_width=True):
        st.session_state["zoom_i"] = max(0, zoom_i - 1); st.session_state["fit"] = False
    if c5.button("➕ Zoom", key="zi", use_container_width=True):
        st.session_state["zoom_i"] = min(len(ZOOMS) - 1, zoom_i + 1); st.session_state["fit"] = False
    st.session_state["fit"] = c6.toggle("Fit width", value=fit, key="fit_t")
    st.session_state["pages_shown"] = st.select_slider("Pages shown at once", [1, 2, 3], value=shown)

    cur = max(1, min(total, cur))
    with st.container(height=720, border=True):
        for p in range(cur, min(total, cur + st.session_state["pages_shown"] - 1) + 1):
            png = pdf_page_png(doc, data, p, 1.6)
            if st.session_state["fit"]:
                st.image(png, width="stretch", caption=f"Page {p} of {total}")
            else:
                st.image(png, width=int(900 * ZOOMS[st.session_state["zoom_i"]]), caption=f"Page {p} of {total}")
    return cur


def pdf_thumbnails(doc: dict, data: bytes, cur: int, total: int) -> int | None:
    """Thumbnails for a window around the current page; clicking jumps."""
    lo = max(1, cur - 3)
    hi = min(total, lo + 7)
    jump = None
    cols = st.columns(2)
    for i, p in enumerate(range(lo, hi + 1)):
        with cols[i % 2]:
            st.image(pdf_page_png(doc, data, p, 0.3), width="stretch")
            if st.button(f"{'▶ ' if p == cur else ''}Page {p}", key=f"th{p}", use_container_width=True):
                jump = p
    return jump


# ------------------------------------------------------------------ reconstructed (docx / pptx)
def render_units(doc: dict, data: bytes, cur: int) -> int:
    parsed = get_parsed(doc, data)
    total = len(parsed.units)
    for n in parsed.notes:
        st.caption("ℹ️ " + n)
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("◀ Prev", key="uv", disabled=cur <= 1, use_container_width=True):
        cur -= 1
    if c2.button("Next ▶", key="un", disabled=cur >= total, use_container_width=True):
        cur += 1
    cur = max(1, min(total, cur))
    c3.markdown(f"**{parsed.unit_label} {cur} of {total}**")
    unit = parsed.units[cur - 1]
    with st.container(height=720, border=True):
        body = unit.html or f"<p>{html.escape(unit.text)}</p>"
        st.html(f"<div class='rx-doc'>{body}</div>")  # st.html sanitises; our text is also escaped
    return cur


# ------------------------------------------------------------------ code / text
def render_code(doc: dict, data: bytes) -> None:
    text = get_text(doc, data)
    lines = text.splitlines() or [""]
    ext = doc["original_name"].rsplit(".", 1)[-1].lower()
    outline = parsers.code_outline(text, ext) if doc["file_type"] == "code" else []

    pages = max(1, -(-len(lines) // CODE_PAGE_LINES))
    start_line = st.session_state.get("code_jump")
    if start_line:
        st.session_state["code_page"] = (start_line - 1) // CODE_PAGE_LINES + 1
        st.session_state["code_jump"] = None
    page = st.session_state.setdefault("code_page", 1)
    page = max(1, min(pages, page))

    c1, c2, c3 = st.columns([1, 1, 3])
    if c1.button("◀", key="cp", disabled=page <= 1):
        page -= 1
    if c2.button("▶", key="cn", disabled=page >= pages):
        page += 1
    st.session_state["code_page"] = page
    c3.caption(f"{len(lines)} lines · block {page}/{pages}")
    lo = (page - 1) * CODE_PAGE_LINES
    chunk = "\n".join(lines[lo:lo + CODE_PAGE_LINES])
    try:
        lexer = get_lexer_for_filename(doc["original_name"])
    except Exception:
        lexer = TextLexer()
    fmt = HtmlFormatter(linenos="table", linenostart=lo + 1, noclasses=True, style="default", nowrap=False)
    with st.container(height=640, border=True):
        st.html(f"<div class='rx-code'>{highlight(chunk, lexer, fmt)}</div>")

    d1, d2 = st.columns(2)
    d1.download_button("⬇ Download source", data, file_name=doc["original_name"], key="dl_code")
    with d2.expander("Copy this block"):
        st.code(chunk, language=ext if ext else None)
    if outline:
        with st.expander(f"Functions & classes ({len(outline)})"):
            for no, name in outline[:80]:
                if st.button(f"{name}  · line {no}", key=f"ol{no}{name}", use_container_width=True):
                    st.session_state["code_jump"] = no
                    st.rerun()
    st.session_state["_code_lines"] = lines


# ------------------------------------------------------------------ tables
def render_table(doc: dict, data: bytes) -> None:
    ft = doc["file_type"]
    sheet = None
    if ft == "xlsx":
        sheets = parsers.excel_sheets(data)
        sheet = st.selectbox("Sheet", sheets, key="sheet")
    df = st.session_state.get("_df")
    if df is None or st.session_state.get("_df_key") != (doc["id"], sheet):
        df = parsers.read_table_preview(data, ft, sheet, get_settings().max_table_rows)
        st.session_state["_df"], st.session_state["_df_key"] = df, (doc["id"], sheet)
    per = 100
    pages = max(1, -(-len(df) // per))
    p = st.number_input("Table page", 1, pages, 1, key="tp")
    st.caption(f"{len(df):,} rows × {len(df.columns)} columns (showing {per} rows per page)")
    st.dataframe(df.iloc[(p - 1) * per:p * per], use_container_width=True, height=520)
    with st.expander("Column summary"):
        st.dataframe(df.describe(include="all").T.astype(str), use_container_width=True)
        col = st.selectbox("Inspect a column", list(df.columns), key="colsel")
        st.write(df[col].value_counts(dropna=False).head(15))
    st.download_button("⬇ Download original", data, file_name=doc["original_name"], key="dl_tbl")


def render_image(doc: dict, data: bytes) -> None:
    st.image(data, width="stretch", caption=doc["original_name"])
    if doc["status"] == "needs_ocr":
        st.info("No text has been extracted from this image yet. Use “Run OCR” in the document header.")
