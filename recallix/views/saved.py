from __future__ import annotations

import streamlit as st

from recallix import db
from recallix.ui import components
from recallix.ui.nav import top_bar
from recallix.views.dashboard import document_card


def render() -> None:
    top_bar()
    st.title("Saved")
    t1, t2, t3 = st.tabs(["Documents", "Answers", "Diagrams"])
    with t1:
        docs = db.list_documents(limit=200, favourites_only=True)
        if not docs:
            st.info("Star a document on the dashboard to keep it here.")
        for d in docs:
            document_card(d, "sv" + d["id"][:8])
    with t2:
        answers = db.list_saved_answers()
        if not answers:
            st.info("Use ⭐ under an AI answer to save it.")
        for a in answers:
            with st.container(border=True):
                st.markdown(f"**{a['title'] or 'Saved answer'}**  ·  {a['created_at'][:10]}")
                components.render_markdown_with_diagrams(a["content"], f"sa{a['id']}")
                if st.button("Remove", key=f"rsa{a['id']}"):
                    db.delete_saved_answer(a["id"])
                    st.rerun()
    with t3:
        diagrams = db.list_saved_diagrams()
        if not diagrams:
            st.info("Generated diagrams you save will appear here.")
        for d in diagrams:
            with st.container(border=True):
                st.markdown(f"**{d['title'] or 'Diagram'}**  ·  {d['created_at'][:10]}")
                components.diagram(d["mermaid_code"], f"sd{d['id']}", allow_save=False)
                if st.button("Remove", key=f"rsd{d['id']}"):
                    db.delete_saved_diagram(d["id"])
                    st.rerun()
