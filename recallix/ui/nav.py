"""Navigation helpers: page routing via session_state, top bar and sidebar menu."""
from __future__ import annotations

import streamlit as st

from recallix import auth, db

PRIVATE_PAGES = {
    "dashboard": "🏠 Dashboard", "workspace": "📖 Workspace", "history": "💬 Chat history",
    "saved": "⭐ Saved", "settings": "⚙️ Settings", "profile": "👤 Profile",
}


def go(page: str, **state) -> None:
    st.session_state["page"] = page
    st.session_state.update(state)
    st.rerun()


def get_prefs_cached() -> dict:
    if "user_prefs" not in st.session_state:
        st.session_state["user_prefs"] = db.get_prefs()
    return st.session_state["user_prefs"]


def show_flash() -> None:
    msg = st.session_state.pop("flash", None)
    if msg:
        st.info(msg)


def brand() -> None:
    st.markdown("<div class='rx-brand'><i></i>Recallix AI</div>", unsafe_allow_html=True)


def top_bar(doc_title: str = "") -> None:
    c_logo, c_doc, c_lang, c_prof, c_out = st.columns([1.3, 3, 1.4, 1, 1])
    with c_logo:
        brand()
    with c_doc:
        if doc_title:
            st.markdown(f"<div class='rx-doc-title'>📄 {doc_title}</div>", unsafe_allow_html=True)
    with c_lang:
        prefs = get_prefs_cached()
        opts = ["english", "tamil", "tanglish"]
        names = {"english": "English", "tamil": "தமிழ் (Tamil)", "tanglish": "Tanglish"}
        choice = st.selectbox("Explanation language", opts, index=opts.index(prefs.get("language", "tanglish")),
                              format_func=lambda x: names[x], label_visibility="collapsed", key="lang_top")
        if choice != prefs.get("language"):
            db.save_prefs(language=choice)
            prefs["language"] = choice
    with c_prof:
        if st.button("👤 Profile", use_container_width=True, key="tb_prof"):
            go("profile")
    with c_out:
        if st.button("Log out", use_container_width=True, key="tb_out"):
            auth.sign_out()
            st.rerun()


def sidebar_menu() -> None:
    with st.sidebar:
        brand()
        st.caption(st.session_state.get("user", {}).get("email", ""))
        for key, label in PRIVATE_PAGES.items():
            kind = "primary" if st.session_state.get("page") == key else "secondary"
            if st.button(label, key=f"nav_{key}", use_container_width=True, type=kind):
                go(key)
        st.divider()
