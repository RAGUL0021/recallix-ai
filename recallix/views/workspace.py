"""Document workspace: viewer (centre), AI chat + voice (right), document navigation (sidebar)."""
from __future__ import annotations

import hashlib

import streamlit as st

from recallix import auth, db, llm, quota, rag, storage
from recallix.diagrams import extract_mermaid, validate_mermaid
from recallix.errors import AppError
from recallix.parsers import ocr_available, pdf_outline
from recallix.security import escape_delimiters
from recallix.services import ingest
from recallix.ui import components, viewer
from recallix.ui.nav import get_prefs_cached, go, sidebar_menu, top_bar

LAYOUTS = {"Balanced": (3, 2.2), "Wide document": (4, 1.6), "Wide chat": (2, 3), "Document only": (1, 0), "Chat only": (0, 1)}
MODES = {"Smart search": rag.MODE_SMART, "This page / slide": rag.MODE_PAGE, "Whole document": rag.MODE_DOC}

QUICK = {
    "Explain this page": ("Explain this {unit} step by step. Define key terms and give one real-world example.", rag.MODE_PAGE),
    "Summarize this page": ("Summarize this {unit} in 5 bullet points.", rag.MODE_PAGE),
    "Summarize the whole document": ("Summarize the whole document: main purpose, key sections, and the 5 most important ideas.", rag.MODE_DOC),
    "Key points & definitions": ("List the key points and important definitions on this {unit}.", rag.MODE_PAGE),
    "Important exam questions": ("Generate 8 important exam questions (with short model answers) from this material.", rag.MODE_SMART),
    "MCQs with answers": ("Create 5 multiple-choice questions with 4 options each, the correct answer, and a one-line explanation.", rag.MODE_SMART),
    "Real-world example": ("Give a simple real-world example for the main concept on this {unit}.", rag.MODE_PAGE),
    "Explain code line by line": ("Explain the code in <document_context> / <selected_text> line by line, then summarize what it does.", rag.MODE_PAGE),
    "Find bugs & suggest fix": ("Review the code for syntax errors, logic errors and risky operations (data deletion, credentials, network). Suggest corrected code and explain why. Do not claim it is correct without reasoning; recommend tests.", rag.MODE_PAGE),
    "Time & space complexity": ("Explain the time and space complexity of the code or algorithm, with a simple example input.", rag.MODE_PAGE),
    "Pseudocode + flowchart": ("Write pseudocode for this logic and a Mermaid flowchart.", rag.MODE_PAGE),
}


def _bytes(doc: dict) -> bytes:
    c = st.session_state.get("_bytes")
    if c and c[0] == doc["id"]:
        return c[1]
    data = storage.download(doc["storage_path"])
    st.session_state["_bytes"] = (doc["id"], data)
    return data


def _unit_noun(doc: dict) -> str:
    return {"pdf": "page", "pptx": "slide", "docx": "section"}.get(doc["file_type"], "part of the document")


# ------------------------------------------------------------------ sidebar
def _sidebar(doc: dict, data: bytes) -> None:
    sidebar_menu()
    with st.sidebar:
        st.markdown("**Layout**")
        st.session_state["layout"] = st.selectbox("Panels", list(LAYOUTS), index=list(LAYOUTS).index(
            st.session_state.get("layout", "Balanced")), label_visibility="collapsed")
        docs = db.list_documents(limit=100)
        names = {d["id"]: d["original_name"] for d in docs}
        ids = list(names)
        if doc["id"] in ids:
            pick = st.selectbox("Document", ids, index=ids.index(doc["id"]), format_func=names.get)
            if pick != doc["id"]:
                go("workspace", doc_id=pick, conv_id=None, cur_unit=1)
        st.divider()
        cur = st.session_state.get("cur_unit", 1)
        ft = doc["file_type"]
        if ft == "pdf":
            total = doc["page_count"]
            st.markdown("**Pages**")
            jump = viewer.pdf_thumbnails(doc, data, cur, total)
            if jump:
                st.session_state["cur_unit"] = jump
                st.rerun()
            c = viewer._cache(doc["id"])
            if "outline" not in c:
                c["outline"] = pdf_outline(data)
            if c["outline"]:
                with st.expander("Outline"):
                    for i, (lvl, title, pg) in enumerate(c["outline"][:80]):
                        if st.button(f"{'  ' * (lvl - 1)}{title} · p.{pg}", key=f"ou{i}", use_container_width=True):
                            st.session_state["cur_unit"] = min(pg, total)
                            st.rerun()
        elif ft in ("docx", "pptx"):
            parsed = viewer.get_parsed(doc, data)
            labels = [f"{u.label}: {u.text[:38].replace(chr(10), ' ')}" for u in parsed.units]
            idx = st.selectbox("Go to", range(len(labels)), index=min(cur, len(labels)) - 1,
                               format_func=lambda i: labels[i])
            if idx + 1 != cur:
                st.session_state["cur_unit"] = idx + 1
                st.rerun()


# ------------------------------------------------------------------ chat
def _submit() -> None:
    q = (st.session_state.get("chat_draft") or "").strip()
    if q:
        st.session_state["pending"] = {"q": q[:4000], "kind": "chat", "mode": MODES[st.session_state.get("ctx_mode", "Smart search")],
                                       "lang": st.session_state.get("q_lang_val")}
        st.session_state["chat_draft"] = ""


def _quick(name: str, doc: dict) -> None:
    tpl, mode = QUICK[name]
    st.session_state["pending"] = {"q": tpl.format(unit=_unit_noun(doc)), "kind": "chat", "mode": mode,
                                   "lang": st.session_state.get("q_lang_val")}


def _selected_text(doc: dict) -> str:
    sel = (st.session_state.get("sel_text") or "").strip()
    if st.session_state.get("use_lines") and doc["file_type"] in ("code", "text", "markdown", "rtf"):
        lines = st.session_state.get("_code_lines") or []
        a, b = int(st.session_state.get("ln_from", 1)), int(st.session_state.get("ln_to", 1))
        part = "\n".join(lines[max(a - 1, 0):max(b, a)])
        sel = (sel + "\n" + part).strip()
    return escape_delimiters(sel)[:8000]


def _process(doc: dict, pending: dict, prefs: dict, cur: int) -> int | None:
    """Runs one AI request. Returns the new assistant message id."""
    quota.check_ai_quota()
    lang = pending.get("lang") or prefs["language"]
    conv_id = st.session_state.get("conv_id")
    if not conv_id:
        conv_id = db.create_conversation(doc["id"], pending["q"][:60])["id"]
        st.session_state["conv_id"] = conv_id
    history = db.recent_messages(conv_id, int(prefs["history_limit"]))
    db.add_message(conv_id, "user", pending["q"], lang)

    context, sources = rag.build_context(doc, pending["q"], cur, pending["mode"])
    selected = _selected_text(doc)
    parts = []
    if context:
        parts.append(f"<document_context>\n{context}\n</document_context>")
    else:
        parts.append("<document_context>(No extractable text is available for this document.)</document_context>")
    if selected:
        parts.append(f"<selected_text>\n{selected}\n</selected_text>")
    parts.append(f"The learner is currently viewing {_unit_noun(doc)} {cur} of '{doc['original_name']}'.")
    if pending["kind"] == "diagram":
        parts.append("Create the requested diagram. Output ONE ```mermaid block, then at most two short sentences "
                     f"describing it in the requested language.\nDiagram request: {pending['q']}")
    else:
        parts.append(f"Learner's request: {pending['q']}")
    parts.append(f"Answer language: {llm.LANGUAGE_NAMES[lang]}.")

    answer = llm.generate(llm.build_system_prompt(lang, prefs["level"]), history, "\n\n".join(parts))
    if pending["kind"] == "diagram":
        code = validate_mermaid(extract_mermaid(answer))  # raises ValidationFailed -> shown as friendly error
        prose = answer.split("```")[0].strip() + ("\n\n" if answer.split("```")[0].strip() else "")
        tail = answer.rsplit("```", 1)[-1].strip()
        answer = f"{prose}```mermaid\n{code}\n```\n\n{tail}".strip()
    msg = db.add_message(conv_id, "assistant", answer, lang, sources)
    db.touch_conversation(conv_id)
    db.record_usage("ai_diagram" if pending["kind"] == "diagram" else "ai_chat")
    return msg["id"]


def _render_message(m: dict, doc: dict, prefs: dict) -> None:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
            return
        components.render_markdown_with_diagrams(m["content"], f"m{m['id']}")
        components.sources_caption(m.get("sources") or [])
        b1, b2, _ = st.columns([1, 1, 2])
        if b1.button("🔊 Read aloud", key=f"ra{m['id']}"):
            st.session_state["tts_msg"] = m["id"]
        if b2.button("⭐ Save", key=f"sv{m['id']}"):
            db.save_answer(m["content"], doc["original_name"][:60], doc["id"])
            st.toast("Saved")
        if st.session_state.get("tts_msg") == m["id"]:
            components.tts_widget(m["content"], prefs["voice_lang"],
                                  autoplay=st.session_state.pop("tts_auto", False), key=str(m["id"]))


def _chat_panel(doc: dict, prefs: dict, cur: int) -> None:
    conv_id = st.session_state.get("conv_id")
    h1, h2 = st.columns([3, 1])
    h1.markdown("#### Ask Recallix")
    if h2.button("New chat", key="newchat", use_container_width=True):
        st.session_state["conv_id"] = None
        st.rerun()

    pending = st.session_state.pop("pending", None)
    box = st.container(height=470, border=True)
    with box:
        msgs = db.list_messages(conv_id) if conv_id else []
        if not msgs and not pending:
            st.caption("Ask about the page you are reading, request a summary, or pick a quick action below.")
        for m in msgs:
            _render_message(m, doc, prefs)
        if pending:
            with st.chat_message("user"):
                st.markdown(pending["q"])
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    try:
                        new_id = _process(doc, pending, prefs, cur)
                        if prefs.get("auto_speak"):
                            st.session_state["tts_msg"], st.session_state["tts_auto"] = new_id, True
                        st.rerun()
                    except AppError as exc:
                        st.error(exc.user_message)

    # quick actions
    is_code = doc["file_type"] in ("code", "text", "markdown")
    keys = list(QUICK)
    default = keys.index("Explain code line by line") if doc["file_type"] == "code" else 0
    q1, q2 = st.columns([3, 1])
    action = q1.selectbox("Quick action", keys, index=default, label_visibility="collapsed")
    q2.button("Run", key="runq", on_click=_quick, args=(action, doc), use_container_width=True)

    with st.expander("Diagram generator"):
        dtype = st.selectbox("Type", ["Flowchart", "Architecture", "Data-flow", "ER diagram", "UML class diagram",
                                      "Sequence diagram", "ML workflow", "Neural network", "Network diagram",
                                      "Concept map", "Mind map", "Process"], key="dtype")
        desc = st.text_input("Describe the diagram", key="ddesc", placeholder="e.g. how login works in this project")
        if st.button("Generate diagram", key="gen_d") and desc.strip():
            st.session_state["pending"] = {"q": f"{dtype}: {desc.strip()}", "kind": "diagram", "mode": rag.MODE_SMART,
                                           "lang": st.session_state.get("q_lang_val")}
            st.rerun()

    with st.expander("Selected text / code lines"):
        st.text_area("Paste a paragraph, formula or code snippet to ask about", key="sel_text", height=80)
        if is_code:
            st.checkbox("Also include code lines", key="use_lines")
            n = len(st.session_state.get("_code_lines") or [1])
            c1, c2 = st.columns(2)
            c1.number_input("From line", 1, max(n, 1), 1, key="ln_from")
            c2.number_input("To line", 1, max(n, 1), min(n, 30), key="ln_to")

    # voice input -> editable draft
    with st.expander("🎤 Voice question"):
        st.caption("Record, then review the text before sending. Uses Gemini for transcription (counts toward your daily AI limit). "
                   "Needs microphone permission; works in current Chrome, Edge, Firefox and Safari.")
        audio = st.audio_input("Record your question", key="mic")
        if audio is not None:
            raw = audio.getvalue()
            h = hashlib.sha1(raw).hexdigest()
            if raw and st.session_state.get("_last_audio") != h:
                st.session_state["_last_audio"] = h
                try:
                    quota.check_ai_quota()
                    with st.spinner("Transcribing…"):
                        text = llm.transcribe(raw, "audio/wav", prefs["voice_lang"])
                    db.record_usage("ai_transcribe")
                    if text:
                        st.session_state["chat_draft"] = text
                        st.success("Transcribed — review it below, then press Send.")
                    else:
                        st.warning("Nothing was recognised. Try again, speak closer to the microphone, or type instead.")
                except AppError as exc:
                    st.error(exc.user_message)
            elif not raw:
                st.warning("The recording was empty. Try again or type your question.")

    st.radio("Search scope", list(MODES), horizontal=True, key="ctx_mode")
    langs = ["english", "tamil", "tanglish"]
    names = {"english": "English", "tamil": "தமிழ்", "tanglish": "Tanglish"}
    lc, _ = st.columns([2, 3])
    st.session_state["q_lang_val"] = lc.selectbox("Answer in", langs, index=langs.index(prefs["language"]),
                                                  format_func=names.get, key=f"qlang_{prefs['language']}")
    st.text_area("Your question", key="chat_draft", height=90, placeholder="Type a question, or use the voice box above…",
                 label_visibility="collapsed")
    st.button("Send", type="primary", on_click=_submit, use_container_width=True, key="send")


# ------------------------------------------------------------------ main
def render() -> None:
    doc_id = st.session_state.get("doc_id")
    doc = db.get_document(doc_id) if doc_id else None
    top_bar(doc["original_name"] if doc else "")
    if not doc:
        sidebar_menu()
        st.title("Document workspace")
        docs = db.list_documents(limit=50)
        if not docs:
            st.info("Upload a document from the dashboard to start.")
        for d in docs:
            if st.button(f"📄 {d['original_name']}", key=f"pick{d['id'][:8]}", use_container_width=True):
                go("workspace", doc_id=d["id"], conv_id=None, cur_unit=1)
        if st.button("Go to dashboard", key="ws_dash"):
            go("dashboard")
        return

    prefs = get_prefs_cached()
    try:
        data = _bytes(doc)
    except AppError as exc:
        sidebar_menu()
        st.error(exc.user_message)
        return

    _sidebar(doc, data)
    cur = st.session_state.get("cur_unit", 1)

    # status banner / actions
    if doc["status"] in ("failed", "needs_ocr", "processing"):
        st.warning(doc["status_detail"] or f"Status: {doc['status']}")
        a, b = st.columns(2)
        if doc["status"] == "needs_ocr" and ocr_available() and a.button("Run OCR (may contain errors)", key="ws_ocr"):
            bar = st.progress(0.0, text="OCR…")
            try:
                ingest.run_ocr(doc["id"], lambda p, m: bar.progress(min(p, 1.0), text=m))
                st.rerun()
            except AppError as exc:
                st.error(exc.user_message)
        if doc["status"] in ("failed", "processing") and b.button("Retry indexing", key="ws_retry"):
            try:
                with st.spinner("Indexing…"):
                    ingest.retry_indexing(doc["id"])
                st.rerun()
            except AppError as exc:
                st.error(exc.user_message)

    ratio = LAYOUTS[st.session_state.get("layout", "Balanced")]
    cols = st.columns([r for r in ratio if r > 0])
    ci = 0
    if ratio[0] > 0:
        with cols[ci]:
            ft = doc["file_type"]
            if ft == "pdf":
                cur = viewer.render_pdf(doc, data, cur, max(doc["page_count"], 1))
                st.download_button("⬇ Download original PDF", data, file_name=doc["original_name"], key="dl_pdf")
            elif ft in ("docx", "pptx"):
                cur = viewer.render_units(doc, data, cur)
                st.download_button("⬇ Download original", data, file_name=doc["original_name"], key="dl_off")
            elif ft in ("code", "text", "markdown", "rtf"):
                viewer.render_code(doc, data)
                cur = ((st.session_state.get("code_page", 1) - 1) * viewer.CODE_PAGE_LINES) // 80 + 1
            elif ft in ("csv", "xlsx"):
                viewer.render_table(doc, data)
            elif ft == "image":
                viewer.render_image(doc, data)
        ci += 1
    st.session_state["cur_unit"] = cur
    if ratio[1] > 0:
        with cols[ci]:
            _chat_panel(doc, prefs, cur)
