from __future__ import annotations

import streamlit as st

from recallix import db
from recallix.errors import AppError
from recallix.ui.nav import go, top_bar


def render() -> None:
    top_bar()
    st.title("Chat history")
    term = st.text_input("Search conversations", placeholder="Search titles and messages…", key="hist_q")
    try:
        convs = db.search_conversations(term.strip()) if term.strip() else db.list_conversations(200)
    except AppError as exc:
        st.error(exc.user_message)
        return
    if not convs:
        st.info("No conversations found.")
    for c in convs:
        k = c["id"][:8]
        with st.container(border=True):
            a, b, c2, d = st.columns([5, 1, 1, 1])
            a.markdown(f"**{c['title']}**  \n<span class='rx-muted'>{c['updated_at'][:16].replace('T', ' ')}"
                       f"{'' if c['document_id'] else ' · document removed'}</span>", unsafe_allow_html=True)
            if b.button("Open", key=f"ho_{k}", type="primary"):
                go("workspace", doc_id=c["document_id"], conv_id=c["id"], cur_unit=1)
            if c2.button("✏️", key=f"hr_{k}", help="Rename"):
                st.session_state[f"hren_{k}"] = True
            if d.button("🗑", key=f"hd_{k}", help="Delete"):
                st.session_state[f"hdel_{k}"] = True
            if st.session_state.get(f"hren_{k}"):
                new = st.text_input("Title", value=c["title"], key=f"hrt_{k}")
                if st.button("Save", key=f"hrs_{k}"):
                    db.rename_conversation(c["id"], new)
                    st.session_state.pop(f"hren_{k}")
                    st.rerun()
            if st.session_state.get(f"hdel_{k}"):
                st.warning("Delete this conversation and all its messages?")
                if st.button("Yes, delete", key=f"hdy_{k}", type="primary"):
                    db.delete_conversation(c["id"])
                    st.session_state.pop(f"hdel_{k}")
                    if st.session_state.get("conv_id") == c["id"]:
                        st.session_state["conv_id"] = None
                    st.rerun()
