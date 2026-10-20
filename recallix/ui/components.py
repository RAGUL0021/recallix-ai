"""Reusable UI widgets: text-to-speech, Mermaid diagrams, chat message rendering."""
from __future__ import annotations

import html
import json
import re

import streamlit as st
import streamlit.components.v1 as components

from recallix import db
from recallix.diagrams import mermaid_html, split_message, validate_mermaid
from recallix.errors import ValidationFailed


def tts_widget(text: str, lang: str = "en-IN", autoplay: bool = False, key: str = "t") -> None:
    """Browser speechSynthesis (no server cost). Voice availability depends on the user's browser/OS."""
    clean = re.sub(r"```.*?```", " code block omitted. ", text, flags=re.S)
    clean = re.sub(r"[*_`#>|]", "", clean)[:3500]
    payload = json.dumps(clean).replace("</", "<\\/")
    lang_js = json.dumps(lang)
    auto = "true" if autoplay else "false"
    components.html(f"""
<div style="font:14px system-ui;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
 <button id="p{key}">🔊 Read aloud</button><button id="s{key}">⏹ Stop</button>
 <select id="v{key}" style="max-width:190px"></select><span id="m{key}" style="color:#555"></span>
</div>
<script>
const text={payload}; let lang={lang_js}; const synth=window.speechSynthesis;
const sel=document.getElementById("v{key}"), msg=document.getElementById("m{key}");
if(!synth){{msg.textContent="Speech is not supported in this browser.";}}
function fill(){{ if(!synth) return; const vs=synth.getVoices(); sel.innerHTML="";
  const pre=lang.split("-")[0]; const m=vs.filter(v=>v.lang.toLowerCase().startsWith(pre));
  (m.length?m:vs).forEach(v=>{{const o=document.createElement("option");o.value=v.name;o.textContent=v.name+" ("+v.lang+")";sel.appendChild(o);}});
  if(!m.length&&vs.length) msg.textContent="No "+lang+" voice installed; using another voice."; }}
if(synth){{fill(); synth.onvoiceschanged=fill;}}
function speak(){{ if(!synth) return; synth.cancel(); const u=new SpeechSynthesisUtterance(text);
  const v=synth.getVoices().find(x=>x.name===sel.value); if(v){{u.voice=v;u.lang=v.lang;}} else u.lang=lang;
  u.onerror=()=>{{msg.textContent="Could not play audio (blocked or unsupported).";}}; synth.speak(u); }}
document.getElementById("p{key}").onclick=speak;
document.getElementById("s{key}").onclick=()=>synth&&synth.cancel();
if({auto}) setTimeout(speak,400);
</script>""", height=48)


def diagram(code: str, key: str, height: int = 420, allow_save: bool = True) -> None:
    try:
        safe = validate_mermaid(code)
    except ValidationFailed as exc:
        st.warning(exc.user_message)
        st.code(code, language="text")
        return
    components.html(mermaid_html(safe), height=height, scrolling=True)
    with st.expander("Diagram source (copyable)"):
        st.code(safe, language="text")
    if allow_save and st.button("⭐ Save diagram", key=f"sd_{key}"):
        db.save_diagram(safe, safe.split("\n", 1)[0][:60])
        st.toast("Diagram saved")


def render_markdown_with_diagrams(text: str, key: str) -> None:
    for i, (kind, body) in enumerate(split_message(text)):
        if kind == "text":
            if body.strip():
                st.markdown(body)
        else:
            diagram(body, f"{key}_{i}")


def sources_caption(sources: list[dict]) -> None:
    if sources:
        st.markdown(
            "<div class='rx-src'><b>Sources consulted:</b> "
            + "; ".join(html.escape(f"[{s['id']}] {s['label']}") for s in sources)
            + "</div>", unsafe_allow_html=True)
