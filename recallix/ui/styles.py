"""Custom CSS. Accessible contrast, Tamil-capable fonts, responsive stacking on small screens."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Noto+Sans+Tamil:wght@400;600&display=swap');
:root{--ink:#14213d;--muted:#4b5a75;--line:#d9e0ec;--paper:#f5f7fb;--accent:#0f766e;--mark:#f59e0b;}
html, body, [class*="st-"], .stMarkdown, button, input, textarea {
  font-family:'Atkinson Hyperlegible','Noto Sans Tamil',system-ui,sans-serif;}
.block-container{padding-top:1.2rem;padding-bottom:2rem;max-width:1500px}
h1,h2,h3{color:var(--ink);letter-spacing:-0.01em}
.rx-brand{font-size:1.45rem;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:.45rem}
.rx-brand i{display:inline-block;width:.8rem;height:.8rem;border-radius:50%;background:var(--accent);
  box-shadow:.55rem 0 0 var(--mark)}
.rx-doc-title{font-weight:700;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rx-muted{color:var(--muted);font-size:.9rem}
.rx-hero{padding:3.2rem 0 1.5rem}
.rx-hero h1{font-size:clamp(2.1rem,5vw,3.6rem);line-height:1.08;max-width:18ch}
.rx-hero p{font-size:1.15rem;color:var(--muted);max-width:56ch}
.rx-sample{border-left:4px solid var(--accent);background:#fff;padding:.7rem 1rem;margin:.6rem 0;border-radius:0 8px 8px 0}
.rx-sample b{color:var(--accent)}
.rx-pill{display:inline-block;padding:.1rem .55rem;border-radius:999px;font-size:.8rem;border:1px solid var(--line);background:#fff}
.rx-ready{border-color:#86efac;background:#f0fdf4}.rx-failed{border-color:#fca5a5;background:#fef2f2}
.rx-needs_ocr,.rx-processing{border-color:#fcd34d;background:#fffbeb}
.rx-src{font-size:.82rem;color:var(--muted)}
.rx-code table{width:100%} .rx-code pre{margin:0;white-space:pre;font-size:.86rem;line-height:1.45}
.rx-doc{background:#fff;padding:1.2rem 1.6rem;border:1px solid var(--line);border-radius:10px;color:#111}
.rx-doc h2,.rx-doc h3,.rx-doc h4,.rx-doc h5{color:#111}
button:focus-visible,[role=tab]:focus-visible{outline:3px solid var(--mark)!important;outline-offset:2px}
@media (max-width:760px){.block-container{padding-left:.6rem;padding-right:.6rem}.rx-hero{padding-top:1.4rem}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
