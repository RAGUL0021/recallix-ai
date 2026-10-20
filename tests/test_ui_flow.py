"""Drives the logged-in UI (dashboard, workspace, chat) with an in-memory fake backend. No network."""
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

LAUNCHER = str(Path(__file__).resolve().parent / "_fake_backend_app.py")


def _at(kind="pdf", page="dashboard"):
    os.environ["FAKE_KIND"] = kind
    at = AppTest.from_file(LAUNCHER, default_timeout=60)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]  # the app turns crashes into st.error banners
    return at


def test_dashboard_lists_document_and_opens_workspace():
    at = _at()
    assert any("book.pdf" in m.value for m in at.markdown)
    next(b for b in at.button if b.label == "Open" and b.key.startswith("o_")).click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert at.session_state["page"] == "workspace"


def test_pdf_workspace_navigation_and_chat_with_sources_and_diagram():
    at = _at("pdf", "workspace")
    at.session_state["doc_id"] = "d1"
    at.session_state["cur_unit"] = 1
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if b.key == "nx").click().run()
    assert at.session_state["cur_unit"] == 2 and not at.error, [e.value for e in at.error]
    at.text_area(key="chat_draft").set_value("What is a loop?")
    next(b for b in at.button if b.key == "send").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    calls = at.session_state["llm_calls"]
    assert len(calls) == 1
    p = calls[0]["prompt"]
    assert "<document_context>" in p and "[S1]" in p and "page 2" in p
    assert "Tanglish" in calls[0]["system"] and "UNTRUSTED" in calls[0]["system"]
    assert any("Sources consulted" in m.value for m in at.markdown)


def test_quick_action_and_code_workspace():
    at = _at("code", "workspace")
    at.session_state["doc_id"] = "d1"
    at.session_state["cur_unit"] = 1
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if b.key == "runq").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert "line by line" in at.session_state["llm_calls"][0]["prompt"]


def test_other_pages_render():
    for page in ("history", "saved", "settings", "profile"):
        at = _at("pdf", page)
        assert not at.exception, (page, [e.value for e in at.exception])


def test_office_and_table_viewers_render():
    for kind in ("docx", "pptx", "xlsx", "csv"):
        at = _at(kind, "workspace")
        at.session_state["doc_id"] = "d1"
        at.session_state["cur_unit"] = 1
        at.run()
        assert not at.exception and not at.error, (kind, [e.value for e in at.error])
