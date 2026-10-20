"""Validate AI-generated Mermaid source and render it safely (strict mode, in a sandboxed iframe)."""
from __future__ import annotations

import json
import re

from recallix.errors import ValidationFailed

ALLOWED_STARTS = ("flowchart", "graph", "sequencediagram", "classdiagram", "erdiagram",
                  "statediagram", "statediagram-v2", "mindmap", "journey", "gantt", "pie", "timeline")
FORBIDDEN = re.compile(
    r"(<\s*/?\s*(script|iframe|object|embed|img|svg|style|link|meta)\b|javascript:|data:text|on\w+\s*=|"
    r"%%\s*\{|^\s*click\s|\bcallback\b|\bhref\b|&#|\\u00|\\x)", re.I | re.M)
FENCE = re.compile(r"```(?:mermaid)?\s*\n(.*?)```", re.S | re.I)
MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(.*?)```", re.S | re.I)
MAX_LEN, MAX_LINES = 6000, 150


def extract_mermaid(text: str) -> str:
    m = FENCE.search(text or "")
    return (m.group(1) if m else (text or "")).strip()


def validate_mermaid(code: str) -> str:
    code = (code or "").strip().replace("\r\n", "\n")
    if not code:
        raise ValidationFailed("The generated diagram was empty.")
    if len(code) > MAX_LEN or code.count("\n") > MAX_LINES:
        raise ValidationFailed("The generated diagram is too large to display safely.")
    first = re.sub(r"^\s*(%%.*\n)*", "", code).split("\n", 1)[0].strip().lower()
    if not first.startswith(ALLOWED_STARTS):
        raise ValidationFailed("The generated text is not a supported diagram type.")
    if FORBIDDEN.search(code):
        raise ValidationFailed("The diagram contained unsafe content and was blocked.")
    return code


def split_message(text: str) -> list[tuple[str, str]]:
    """[('text', ...), ('mermaid', code), ...] so chat can render diagrams inline."""
    out, pos = [], 0
    for m in MERMAID_BLOCK.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        out.append(("mermaid", m.group(1).strip()))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def mermaid_html(code: str, element_id: str = "d") -> str:
    """Self-contained page for st.components.v1.html. The source is JSON-encoded (never concatenated as HTML)."""
    payload = json.dumps(code).replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;font-family:system-ui,sans-serif;background:#fff}} #{element_id}{{padding:8px;overflow:auto}}
.err{{color:#b42318;font:13px system-ui;padding:8px}} button{{margin:6px;padding:4px 10px;border:1px solid #bbb;border-radius:6px;background:#f7f7f7;cursor:pointer}}
</style></head><body>
<div id="{element_id}">Rendering diagram…</div>
<button id="dl" style="display:none">Download SVG</button>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<script>
(async () => {{
  const src = {payload};
  const box = document.getElementById("{element_id}");
  try {{
    mermaid.initialize({{startOnLoad:false, securityLevel:"strict", theme:"default", flowchart:{{htmlLabels:false}}}});
    await mermaid.parse(src);
    const {{svg}} = await mermaid.render("g_" + Date.now(), src);
    box.innerHTML = svg;
    const b = document.getElementById("dl"); b.style.display = "inline-block";
    b.onclick = () => {{ const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([svg], {{type:"image/svg+xml"}})); a.download = "diagram.svg"; a.click(); }};
  }} catch (e) {{
    box.innerHTML = '<div class="err">This diagram has a syntax error and could not be drawn. The source is shown below the diagram.</div>';
  }}
}})();
</script></body></html>"""
