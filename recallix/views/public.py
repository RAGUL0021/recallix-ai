"""Landing, sign-up, login, forgot/reset password, legal."""
from __future__ import annotations

import streamlit as st

from recallix import auth
from recallix.errors import AppError
from recallix.ui.nav import brand, go, show_flash


def _top() -> None:
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    with c1:
        brand()
    if c2.button("Features", use_container_width=True, key="pb_home"):
        go("landing")
    if c3.button("Log in", use_container_width=True, key="pb_login"):
        go("login")
    if c4.button("Sign up", type="primary", use_container_width=True, key="pb_signup"):
        go("signup")
    show_flash()


def landing() -> None:
    _top()
    st.markdown("""<div class='rx-hero'><h1>Read it once. Understand it in your own language.</h1>
<p>Upload a PDF, slide deck, spreadsheet or source file. Recallix shows the original, answers your questions
with page references, and explains in English, Tamil or Tanglish — typed or spoken.</p></div>""", unsafe_allow_html=True)
    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button("Create free account", type="primary", use_container_width=True, key="h_signup"):
        go("signup")
    if c2.button("Log in", use_container_width=True, key="h_login"):
        go("login")

    st.markdown("#### The same idea, three ways")
    st.markdown("""<div class='rx-sample'><b>English</b> — A loop repeats a block of code while a condition is satisfied.</div>
<div class='rx-sample'><b>தமிழ்</b> — ஒரு குறிப்பிட்ட code-ஐ மீண்டும் மீண்டும் இயக்க loop பயன்படுகிறது.</div>
<div class='rx-sample'><b>Tanglish</b> — Loop na oru code block-a thirumba thirumba execute panna use pannuvom.</div>""",
                unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.markdown("**Keep the document in view**\n\nPDFs open page by page beside the chat, so you never lose your place.")
    b.markdown("**Answers with sources**\n\nLong books are searched first, and replies list the pages they used.")
    c.markdown("**Code tutor and diagrams**\n\nLine-by-line code explanations, bug hunting, and flowcharts you can download.")
    st.caption("Free accounts have daily AI limits. Your files are private to your account.")
    if st.button("Privacy policy & terms", key="h_legal"):
        go("legal")


def signup() -> None:
    _top()
    st.subheader("Create your account")
    with st.form("signup_form"):
        name = st.text_input("Display name")
        email = st.text_input("Email")
        pw = st.text_input("Password", type="password", help="At least 8 characters with a letter and a number.")
        agree = st.checkbox("I agree to the Terms and Privacy Policy")
        ok = st.form_submit_button("Create account", type="primary")
    if ok:
        if not agree:
            st.error("Please accept the Terms and Privacy Policy to continue.")
        else:
            try:
                st.success(auth.sign_up(email, pw, name))
            except AppError as exc:
                st.error(exc.user_message)
    if st.button("Already registered? Log in", key="su_login"):
        go("login")


def login() -> None:
    _top()
    st.subheader("Welcome back")
    with st.form("login_form"):
        email = st.text_input("Email")
        pw = st.text_input("Password", type="password")
        ok = st.form_submit_button("Log in", type="primary")
    if ok:
        try:
            auth.sign_in(email, pw)
            st.session_state["page"] = "dashboard"
            st.rerun()
        except AppError as exc:
            st.error(exc.user_message)
    c1, c2 = st.columns(2)
    if c1.button("Forgot password?", key="li_forgot"):
        go("forgot")
    if c2.button("Create an account", key="li_signup"):
        go("signup")


def forgot() -> None:
    _top()
    st.subheader("Reset your password")
    with st.form("forgot_form"):
        email = st.text_input("Email")
        ok = st.form_submit_button("Send reset link", type="primary")
    if ok:
        try:
            st.success(auth.send_password_reset(email))
        except AppError as exc:
            st.error(exc.user_message)
    if st.button("Back to log in", key="fg_back"):
        go("login")


def reset() -> None:
    """Shown after the user clicks the recovery link (session already established by verify_otp)."""
    brand()
    if not auth.is_logged_in():
        st.error("This reset link is invalid or has expired.")
        if st.button("Request a new link"):
            go("forgot")
        return
    st.subheader("Choose a new password")
    with st.form("reset_form"):
        pw = st.text_input("New password", type="password")
        pw2 = st.text_input("Repeat new password", type="password")
        ok = st.form_submit_button("Save password", type="primary")
    if ok:
        if pw != pw2:
            st.error("The two passwords do not match.")
        else:
            try:
                auth.update_password(pw)
                st.session_state["flash"] = "Password updated."
                go("dashboard")
            except AppError as exc:
                st.error(exc.user_message)


LEGAL = """
### Privacy policy (template — have it reviewed before launch)
**What we store.** Your email and display name, the files you upload, text extracted from them, search embeddings,
your chat history, saved answers and diagrams, and usage counters used to enforce limits.

**Who can see it.** Only you. Data is protected by per-user access rules in the database and private file storage.
The site operator can technically access the database, so do not upload data you are not allowed to share.

**AI processing.** Questions and relevant excerpts of your documents are sent to Google's Gemini API to produce answers.
Voice recordings you make with the microphone button are sent to Gemini for transcription. Browser read-aloud runs on your device.
Review Google's terms for how API data is handled.

**Deletion.** Deleting a document removes its stored file, extracted text and embeddings. Deleting a conversation removes its messages.

**Retention.** Data stays until you delete it. Contact the site owner to remove your account entirely.

### Terms of use
Use the service lawfully and only upload material you have the right to use. Do not upload malware, attempt to access other
users' data, or abuse the AI quotas. AI answers can be wrong — verify important facts and test any code before relying on it.
The service is provided as-is, with daily usage limits that may change.
"""


def legal() -> None:
    _top()
    st.markdown(LEGAL)
