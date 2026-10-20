"""Render the real app headlessly with Streamlit's AppTest (no network needed)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _run(env: dict):
    import os

    from recallix import config

    for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "GEMINI_API_KEY"):
        os.environ.pop(k, None)
    os.environ.update(env)
    config.get_settings.cache_clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def test_missing_config_shows_setup_screen():
    at = _run({})
    assert not at.exception
    assert any("Missing configuration" in e.value for e in at.error)


def test_landing_page_renders_and_login_navigation_works():
    at = _run({"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon", "GEMINI_API_KEY": "k"})
    assert not at.exception
    assert any("Read it once" in m.value for m in at.markdown)
    next(b for b in at.button if b.key == "h_login").click().run()
    assert not at.exception
    assert any(f.label == "Email" for f in at.text_input)
    # invalid input is rejected before any network call
    at.text_input[0].set_value("not-an-email")
    at.text_input[1].set_value("x")
    next(b for b in at.button if b.label == "Log in" and b.key != "pb_login").click().run()
    assert at.error and "email" in at.error[0].value.lower()
