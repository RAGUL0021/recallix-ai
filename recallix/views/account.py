"""Settings and profile pages."""
from __future__ import annotations

import streamlit as st

from recallix import auth, db, quota
from recallix.errors import AppError
from recallix.services import ingest
from recallix.ui.nav import top_bar

VOICE_LANGS = {"en-IN": "English (India)", "en-US": "English (US)", "en-GB": "English (UK)", "ta-IN": "Tamil (India)"}


def settings() -> None:
    top_bar()
    st.title("Settings")
    prefs = db.get_prefs()
    with st.form("prefs"):
        langs = ["english", "tamil", "tanglish"]
        lang = st.selectbox("Explanation language", langs, index=langs.index(prefs["language"]),
                            format_func=str.title)
        levels = ["beginner", "intermediate", "advanced"]
        level = st.selectbox("My level", levels, index=levels.index(prefs["level"]), format_func=str.title)
        vkeys = list(VOICE_LANGS)
        vl = st.selectbox("Read-aloud language", vkeys,
                          index=vkeys.index(prefs["voice_lang"]) if prefs["voice_lang"] in vkeys else 0,
                          format_func=VOICE_LANGS.get,
                          help="Tamil voices must be installed on your device/browser. Tanglish is read with an English voice and may sound unnatural.")
        auto = st.checkbox("Read answers aloud automatically (some browsers still block autoplay)",
                           value=prefs["auto_speak"])
        hist = st.slider("Messages of history sent to the AI", 2, 30, int(prefs["history_limit"]))
        if st.form_submit_button("Save settings", type="primary"):
            db.save_prefs(language=lang, level=level, voice_lang=vl, auto_speak=auto, history_limit=hist)
            st.session_state.pop("user_prefs", None)
            st.success("Settings saved.")
    st.subheader("Usage and limits")
    try:
        u = quota.snapshot()
        st.progress(min(u["ai_today"] / max(u["ai_limit"], 1), 1.0), text=f"AI requests today: {u['ai_today']} / {u['ai_limit']}")
        st.progress(min(u["storage_mb"] / max(u["storage_limit_mb"], 1), 1.0), text=f"Storage: {u['storage_mb']:.1f} / {u['storage_limit_mb']} MB")
    except AppError as exc:
        st.error(exc.user_message)
    st.subheader("Danger zone")
    with st.expander("Delete all my documents and conversations"):
        st.warning("This permanently deletes every document (files, extracted text, embeddings), conversation and saved item.")
        if st.checkbox("I understand", key="del_all_ok") and st.button("Delete everything", type="primary"):
            for d in db.list_documents(limit=1000):
                ingest.delete_document(d["id"])
            for c in db.list_conversations(1000):
                db.delete_conversation(c["id"])
            for a in db.list_saved_answers():
                db.delete_saved_answer(a["id"])
            for g in db.list_saved_diagrams():
                db.delete_saved_diagram(g["id"])
            st.success("All your content was deleted.")
    st.caption("To delete the account itself, contact the site owner.")


def profile() -> None:
    top_bar()
    st.title("Profile")
    prof = db.get_profile()
    user = st.session_state["user"]
    st.markdown(f"**Email:** {user['email']}  \n**User ID:** `{user['id']}`  \n**Member since:** {user['created_at']}")
    with st.form("prof"):
        name = st.text_input("Display name", value=prof.get("display_name", ""), max_chars=80)
        if st.form_submit_button("Save", type="primary"):
            db.update_display_name(name)
            st.success("Profile updated.")
    st.subheader("Change password")
    with st.form("pw"):
        p1 = st.text_input("New password", type="password")
        p2 = st.text_input("Repeat new password", type="password")
        if st.form_submit_button("Update password"):
            if p1 != p2:
                st.error("The two passwords do not match.")
            else:
                try:
                    auth.update_password(p1)
                    st.success("Password updated.")
                except AppError as exc:
                    st.error(exc.user_message)
