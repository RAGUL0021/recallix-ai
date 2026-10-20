"""Authentication via Supabase Auth.

SECURITY MODEL
* Each browser session gets its OWN Supabase client (stored in st.session_state, never cached globally),
  authenticated with that user's JWT. Every database/storage call therefore runs under Row Level Security.
* Only the public ANON key is used. The service-role key is never needed or loaded by this app.
* The user id is always read from the verified session, never from browser-supplied input.
"""
from __future__ import annotations

import streamlit as st
from supabase import Client, create_client

from recallix.config import get_settings
from recallix.errors import AuthFailed, ServiceUnavailable, get_logger
from recallix.security import validate_email, validate_password

log = get_logger("auth")


def _new_client() -> Client:
    s = get_settings()
    try:
        return create_client(s.supabase_url, s.supabase_anon_key)
    except Exception as exc:
        log.error("Supabase client creation failed: %s", type(exc).__name__)
        raise ServiceUnavailable("Cannot reach the database service. Check the Supabase URL and key.") from exc


def anon_client() -> Client:
    """Per-session client used for sign-up / sign-in flows."""
    if "sb" not in st.session_state:
        st.session_state["sb"] = _new_client()
    return st.session_state["sb"]


def _friendly(exc: Exception) -> str:
    msg = str(exc).lower()
    if "invalid login" in msg or "invalid credentials" in msg:
        return "Email or password is incorrect."
    if "not confirmed" in msg:
        return "Please verify your email first. Check your inbox for the confirmation link."
    if "rate limit" in msg or "too many" in msg or "over_email_send_rate_limit" in msg:
        return "Too many attempts. Please wait a few minutes and try again."
    if "expired" in msg or "invalid" in msg and "token" in msg:
        return "This link is invalid or has expired. Request a new one."
    if "weak" in msg or "password" in msg:
        return "That password was rejected. Choose a longer, less common password."
    if "network" in msg or "connect" in msg or "timeout" in msg:
        return "Network problem while contacting the login service. Try again."
    return "Something went wrong. Please try again."


def _set_user_from_session(client: Client) -> None:
    sess = client.auth.get_session()
    if not sess or not sess.user:
        raise AuthFailed("Your session could not be established.")
    u = sess.user
    st.session_state["user"] = {"id": u.id, "email": u.email or "", "created_at": str(u.created_at)[:10]}


def sign_up(email: str, password: str, display_name: str) -> str:
    email = (email or "").strip().lower()
    if not validate_email(email):
        raise AuthFailed("Enter a valid email address.")
    problem = validate_password(password)
    if problem:
        raise AuthFailed(problem)
    try:
        anon_client().auth.sign_up({
            "email": email, "password": password,
            "options": {"data": {"display_name": (display_name or "").strip()[:80]},
                        "email_redirect_to": get_settings().app_url},
        })
    except Exception as exc:
        log.warning("sign_up failed: %s", type(exc).__name__)
        raise AuthFailed(_friendly(exc)) from exc
    # Same message whether or not the address already exists (prevents account enumeration).
    return "Check your inbox. If this email can be registered, a verification link is on its way."


def sign_in(email: str, password: str) -> None:
    email = (email or "").strip().lower()
    if not validate_email(email) or not password:
        raise AuthFailed("Enter your email and password.")
    client = _new_client()  # fresh client => no leftover session from another user
    try:
        client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        log.warning("sign_in failed: %s", type(exc).__name__)
        raise AuthFailed(_friendly(exc)) from exc
    st.session_state["sb"] = client
    _set_user_from_session(client)


def send_password_reset(email: str) -> str:
    email = (email or "").strip().lower()
    if not validate_email(email):
        raise AuthFailed("Enter a valid email address.")
    try:
        anon_client().auth.reset_password_for_email(email, {"redirect_to": get_settings().app_url})
    except Exception as exc:
        log.warning("reset failed: %s", type(exc).__name__)
        raise AuthFailed(_friendly(exc)) from exc
    return "If an account exists for that email, a reset link has been sent."


def verify_token_hash(token_hash: str, kind: str) -> str:
    """Handles ?token_hash=...&type=signup|email|recovery links from the email templates."""
    if kind not in ("signup", "email", "recovery"):
        raise AuthFailed("Unsupported link type.")
    client = _new_client()
    try:
        client.auth.verify_otp({"token_hash": token_hash, "type": kind})
    except Exception as exc:
        log.warning("verify_otp failed: %s", type(exc).__name__)
        raise AuthFailed(_friendly(exc)) from exc
    st.session_state["sb"] = client
    _set_user_from_session(client)
    return kind


def update_password(new_password: str) -> None:
    problem = validate_password(new_password)
    if problem:
        raise AuthFailed(problem)
    try:
        client().auth.update_user({"password": new_password})
    except Exception as exc:
        raise AuthFailed(_friendly(exc)) from exc


def sign_out() -> None:
    try:
        st.session_state.get("sb") and st.session_state["sb"].auth.sign_out()
    except Exception:
        pass
    st.session_state.clear()


def is_logged_in() -> bool:
    """True only if a live, non-expired session exists. get_session() refreshes tokens when needed."""
    sb = st.session_state.get("sb")
    if sb is None or "user" not in st.session_state:
        return False
    try:
        sess = sb.auth.get_session()
    except Exception:
        sess = None
    if not sess or not sess.user:
        st.session_state.clear()
        st.session_state["flash"] = "Your session expired. Please log in again."
        return False
    return True


def client() -> Client:
    """The authenticated, RLS-scoped client for the current session."""
    if not is_logged_in():
        raise AuthFailed("Please log in to continue.")
    return st.session_state["sb"]


def user_id() -> str:
    if not is_logged_in():
        raise AuthFailed("Please log in to continue.")
    return st.session_state["user"]["id"]
