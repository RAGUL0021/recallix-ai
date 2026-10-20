"""Recallix AI — entry point and page router. Run with:  streamlit run app.py"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Recallix AI", page_icon="📖", layout="wide", initial_sidebar_state="expanded")

from recallix import auth  # noqa: E402
from recallix.config import get_settings  # noqa: E402
from recallix.errors import AppError, get_logger  # noqa: E402
from recallix.ui import styles  # noqa: E402
from recallix.ui.nav import go  # noqa: E402
from recallix.views import account, dashboard, history, public, saved, workspace  # noqa: E402

log = get_logger("app")
styles.inject()

PUBLIC = {"landing": public.landing, "login": public.login, "signup": public.signup,
          "forgot": public.forgot, "legal": public.legal}
PRIVATE = {"dashboard": dashboard.render, "workspace": workspace.render, "history": history.render,
           "saved": saved.render, "settings": account.settings, "profile": account.profile}


def _hide_sidebar() -> None:
    st.markdown("<style>[data-testid=stSidebar],[data-testid=stSidebarCollapsedControl]{display:none}</style>",
                unsafe_allow_html=True)


def _setup_screen(missing: list[str]) -> None:
    st.title("Recallix AI needs setup")
    st.error("Missing configuration: " + ", ".join(missing))
    st.markdown("Add these values to your `.env` file (local) or to the app's **Secrets** (Streamlit Cloud). "
                "See README.md, section 4.")
    st.stop()


def _handle_email_link() -> None:
    qp = st.query_params
    token, kind = qp.get("token_hash"), qp.get("type")
    if not (token and kind):
        return
    try:
        result = auth.verify_token_hash(token, kind)
        st.query_params.clear()
        if result == "recovery":
            st.session_state["page"] = "reset"
        else:
            st.session_state["page"] = "dashboard"
            st.session_state["flash"] = "Email verified. Welcome to Recallix AI!"
    except AppError as exc:
        st.query_params.clear()
        st.session_state["page"] = "login"
        st.session_state["flash"] = exc.user_message
    st.rerun()


def main() -> None:
    missing = get_settings().missing()
    if missing:
        _setup_screen(missing)
    _handle_email_link()

    page = st.session_state.get("page", "landing")
    logged_in = auth.is_logged_in()

    if page == "reset":
        _hide_sidebar()
        public.reset()
        return
    if logged_in:
        if page not in PRIVATE:
            page = "dashboard"
        st.session_state["page"] = page
        PRIVATE[page]()
    else:
        if page not in PUBLIC:
            page = "login"
        st.session_state["page"] = page
        _hide_sidebar()
        PUBLIC[page]()


try:
    main()
except AppError as exc:
    st.error(exc.user_message)
except Exception as exc:  # noqa: BLE001 - never show raw stack traces to users
    if type(exc).__name__ in ("RerunException", "StopException"):
        raise
    log.exception("Unhandled error")
    st.error("Something went wrong on our side. Please refresh the page and try again.")
