# Recallix AI — Smart Document Reader, Voice Assistant & Coding Tutor

A public, multi-user Streamlit app. Users sign up, upload documents, read them page by page, and ask Gemini questions
in **English, Tamil or Tanglish** (typed or spoken). Every user has a private workspace.

**Stack:** Streamlit · Supabase (Auth + Postgres + private Storage + pgvector) · Google Gemini (`google-genai`) ·
PyMuPDF · python-docx · python-pptx · pandas/openpyxl · Pillow + Tesseract OCR · Pygments · Mermaid.

```
app.py                      entry point + router + global error handling
recallix/
  config.py                 settings from .env / Streamlit secrets
  auth.py                   Supabase Auth, per-session RLS-scoped client
  db.py  storage.py         data access (always under the user's JWT -> RLS)
  quota.py                  per-user rate limits and daily quotas
  security.py               filename/content validation, prompt-delimiter escaping
  parsers.py chunking.py    PDF/DOCX/PPTX/code/CSV/XLSX/image -> units -> chunks
  llm.py rag.py             Gemini calls, embeddings, retrieval, prompts
  diagrams.py               Mermaid validation + sandboxed rendering
  services/ingest.py        upload -> validate -> store -> chunk -> embed (+ OCR, retry, delete)
  ui/  views/               styles, viewer, widgets, and every page
supabase/migrations/001_schema.sql    tables, indexes, RLS, vector search, storage policies
tests/                      unit tests, UI-flow tests, two-user RLS isolation test
docs/email-templates.md     required Supabase email template edits
```

---

## 1. Install the tools (Windows)

1. **Python 3.12** from python.org. Tick **"Add python.exe to PATH"** in the installer.
2. **VS Code** from code.visualstudio.com, then install the **Python** extension.
3. **Git** from git-scm.com.
4. *(Optional, only for OCR of scanned files)* **Tesseract**: install the Windows build from
   github.com/UB-Mannheim/tesseract/wiki, tick the Tamil language data during setup, and add
   `C:\Program Files\Tesseract-OCR` to your PATH. Without it everything works except OCR.

## 2. Open the project and create a virtual environment

Unzip the project, then in VS Code: **File → Open Folder → recallix-ai**. Open a terminal (**Terminal → New Terminal**):

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
```
If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then retry.
In VS Code press `Ctrl+Shift+P` → "Python: Select Interpreter" → choose the one inside `venv`.

## 3. Create the Supabase project

1. Sign up at supabase.com → **New project**. Save the database password.
2. **SQL Editor → New query** → paste all of `supabase/migrations/001_schema.sql` → **Run**.
   (This creates the tables, Row Level Security policies, vector search function and the private `documents` bucket.)
3. **Project Settings → API**: copy the **Project URL** and the **anon public** key.
   Do **not** use or share the `service_role` key — this app never needs it.
4. **Authentication → Providers → Email**: keep "Confirm email" **on**.
5. Follow **`docs/email-templates.md`** (changes the two email links and sets the Site URL). Email verification and password reset
   will not work until you do this.

## 4. Get a Gemini API key and configure the app

1. Create a key in **Google AI Studio** (aistudio.google.com → Get API key).
2. Copy `.env.example` to `.env` and fill in the three required values:
   ```
   SUPABASE_URL=...
   SUPABASE_ANON_KEY=...
   GEMINI_API_KEY=...
   ```
3. Model names change. The default is `gemini-2.5-flash` (chat) and `gemini-embedding-001` (embeddings, 768 dimensions).
   Check https://ai.google.dev/gemini-api/docs/models and change `GEMINI_MODEL` in `.env` if needed. Do **not** change the
   embedding dimension without also changing `vector(768)` in the SQL.

## 5. Run it

```powershell
streamlit run app.py
```
Open http://localhost:8501 → **Sign up** → click the link in the verification email → upload a PDF → ask a question.

## 6. Run the tests

```powershell
python -m pytest -q
```
* Unit tests, UI-flow tests (fake backend) and smoke tests run with no accounts or internet.
* **Two-user isolation test** (`tests/test_rls_isolation.py`) needs your real Supabase project. In Supabase →
  Authentication → Users → **Add user** (tick *Auto Confirm*) twice, then set in your terminal:
  ```powershell
  $env:TEST_USER_A_EMAIL="a@example.com"; $env:TEST_USER_A_PASSWORD="..."
  $env:TEST_USER_B_EMAIL="b@example.com"; $env:TEST_USER_B_PASSWORD="..."
  python -m pytest tests/test_rls_isolation.py -q
  ```
  It checks that user B cannot read, change, delete, search, or download user A's documents, chunks, messages or files,
  and cannot reset their own usage counters. **Run it before you go public.**

## 7. Put it on GitHub and deploy (Streamlit Community Cloud)

```powershell
git init
git add .
git commit -m "Recallix AI"
```
Create an empty repo on github.com and follow its "push an existing repository" commands. `.env` and `secrets.toml` are in
`.gitignore`; check `git status` shows neither before you push.

1. share.streamlit.io → **Create app** → pick the repo → main file `app.py`.
2. **Advanced settings → Secrets**: paste the contents of `.streamlit/secrets.toml.example` with your real values and
   `APP_URL` set to the app's final `https://….streamlit.app` URL.
3. Back in Supabase set **Site URL** and **Redirect URLs** to that same URL.
4. `packages.txt` makes Streamlit Cloud install Tesseract (English + Tamil) automatically.

## 8. Usage limits (all configurable in `.env` / Secrets)

| Setting | Default | Meaning |
|---|---|---|
| `MAX_UPLOAD_MB` | 25 | per file (also set `maxUploadSize` in `.streamlit/config.toml`, and the bucket limit in the SQL) |
| `MAX_STORAGE_MB` / `MAX_DOCUMENTS` | 200 / 50 | per user |
| `DAILY_AI_LIMIT` / `HOURLY_AI_LIMIT` | 60 / 25 | chat + diagram + voice transcription requests per user |
| `DAILY_EMBED_CHUNK_LIMIT` | 4000 | text chunks indexed per user per day (roughly a 1,000-page book) |

## 9. How the key requirements are met

* **Per-user privacy.** The app uses only the anon key. Each browser session gets its own Supabase client signed in with that
  user's JWT, so *every* query runs under Row Level Security. Policies exist on all 9 tables; chunks and messages also verify
  that the parent document/conversation belongs to the same user. Storage paths must start with the user's own id.
  The `match_chunks` search function is `SECURITY INVOKER`, so RLS applies to vector search too.
* **Quotas can't be reset by users:** `usage_events` has no UPDATE/DELETE policy.
* **Uploads:** content sniffing (PDF header, Office zip structure, image signatures, no binary in text files), zip-bomb and macro
  rejection, sanitised display names, random UUID storage names, duplicate detection by SHA-256, per-user size limits. Uploaded files
  are parsed, **never executed**.
* **Prompt injection:** document text is wrapped in `<document_context>`, delimiter look-alikes are stripped, and the system prompt
  tells the model to treat it as untrusted data. This reduces the risk; no prompt defence is perfect.
* **Source references** are computed by the app from the chunks it actually retrieved and shown as "Sources consulted";
  the model only cites `[S#]` labels it was given.
* **Diagrams:** Gemini output is validated (allow-listed diagram types; script/HTML/`click`/`%%{init}` blocked), then drawn by
  Mermaid in `securityLevel: "strict"` inside a sandboxed iframe.
* **Errors:** users see friendly messages; details go to the server log (never passwords, tokens or document text).

## 10. Honest limitations — please read

* **Not yet run against live services.** I tested parsing, chunking, validation, diagram safety, and the full UI flow using a fake
  backend. I could **not** test real Supabase signup/email, real Gemini calls, or RLS on your project from here. Expect to fix small
  things on first run. Use the isolation test (step 6) to verify RLS yourself.
* **Browser refresh logs you out.** The session lives in Streamlit's per-tab server session. Sessions auto-refresh while the tab is
  open, but pressing F5 or opening a new tab requires logging in again. (A cookie-based persistent session needs an extra
  component and is not included.)
* **PDF viewer** renders pages as images with PyMuPDF (fast, low-memory, only visible pages are rendered) rather than embedding
  PDF.js. You get page navigation, zoom, fit-width, thumbnails, outline and download, but **no in-viewer text selection or search**.
  Use "Selected text" in the chat panel to paste a passage.
* **Word / PowerPoint** are *reconstructed* views (text, tables, images), not the original page layout; the app says so in the UI.
  Legacy **.doc / .ppt / .xls are rejected** with a message to re-save as .docx/.pptx/.xlsx; reliable parsing needs LibreOffice.
* **OCR** quality depends on scan quality and installed languages; results are labelled as possibly containing errors.
  Scanned pages are OCR'd only after the user clicks *Run OCR* (limit `MAX_OCR_PAGES`).
* **Voice.** Speech-to-text records audio in the browser (`st.audio_input`) and transcribes it with Gemini, so it works in any modern
  browser that allows the microphone, but it is record-then-transcribe, not live dictation, and uses your AI quota.
  Read-aloud uses the browser's built-in speech engine (free). Tamil voices exist only if the user's OS/browser has one installed,
  and **Tanglish is read with an English voice, so pronunciation is imperfect.** Autoplay is off by default and many browsers
  block it even when enabled.
* **Tanglish quality** is prompt-driven and depends on the model; review output before relying on it for teaching.
* **Large-book "summarize everything"** uses ~28 evenly spaced chunks, so it is an overview, not exhaustive. Ask section-specific questions for detail.
* **Account deletion** (removing the login itself) needs the service-role key, which this app deliberately doesn't hold. Users can
  delete all their content from Settings; deleting the account is done by you in the Supabase dashboard.
* **Streamlit Community Cloud** has modest memory/CPU; very large PDFs or many simultaneous users may need a bigger host.
* **Costs.** Gemini usage, Supabase storage/egress and an email provider may cost money beyond free tiers. Keep the quotas on.
* The privacy policy and terms are **templates**, not legal advice.
* Nothing here is "fully secure" — treat the checklist and isolation test as a start, and review before a large public launch.

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| "Recallix AI needs setup" | `.env` / Secrets is missing one of the three required values |
| "Email or password is incorrect" right after signup | verify your email first |
| Verification / reset link does nothing | email templates not edited (docs/email-templates.md) or Site URL wrong |
| "AI model is not available" | update `GEMINI_MODEL` |
| Document stuck on "failed" | open it and press **Retry indexing** (usually a quota/API hiccup) |
| `type "extensions.vector" does not exist` | re-run the SQL; the `vector` extension must exist in schema `extensions` |
| OCR button missing | Tesseract not installed / not on PATH |
