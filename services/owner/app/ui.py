"""UI helpers; the owner and provider images carry identical copies.

copy_block() shows values with a Copy button. mask=True hides the value, because
hand-selected long hex is error-prone; the values are public, not secret.

Not st.code(): its icon needs navigator.clipboard, absent on plain http origins. Streamlit
strips onclick but runs <script>, so one delegated listener reads data-copy, falling back
to execCommand. If Streamlit lacks unsafe_allow_javascript, a visible code block is used.
"""

import html as _html

import streamlit as st

_MASK = "•" * 24

_ASSETS = """<style>
.zk-copy { margin: 0 0 .55rem 0; }
.zk-copy-label { display: block; font-size: .78rem; opacity: .7; margin-bottom: .15rem; }
.zk-copy-row { display: flex; gap: .4rem; align-items: flex-start; }
.zk-copy-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .8rem; word-break: break-all; padding: .3rem .5rem;
  border-radius: .4rem; background: rgba(128,128,128,.14);
  flex: 1; min-width: 0;
}
.zk-copy-value.zk-compact { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; word-break: normal; }
.zk-copy-value.zk-masked { letter-spacing: .12em; opacity: .75; user-select: none; -webkit-user-select: none; white-space: nowrap; overflow: hidden; }
.zk-copy-btn {
  flex: none; cursor: pointer; font: inherit; font-size: .78rem; padding: .28rem .6rem;
  border-radius: .4rem; border: 1px solid rgba(128,128,128,.45); background: transparent; color: inherit;
}
.zk-copy-btn:hover { background: rgba(128,128,128,.2); }
.zk-copy-btn:focus-visible { outline: 2px solid rgba(128,128,128,.8); }
</style>
<script>
if (!window.__zkCopyInstalled) {
  window.__zkCopyInstalled = true;
  document.addEventListener('click', async function (ev) {
    const btn = ev.target.closest && ev.target.closest('.zk-copy-btn');
    if (!btn) return;
    const text = btn.getAttribute('data-copy');
    let ok = false;
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {}
    }
    if (!ok) {                                   // plain-http origins have no navigator.clipboard
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;';
      document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, text.length);
      try { ok = document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta);
    }
    const orig = btn.getAttribute('data-orig') || btn.textContent;
    btn.setAttribute('data-orig', orig);
    btn.textContent = ok ? 'Copied' : 'Copy failed';
    setTimeout(function () { btn.textContent = orig; }, 1500);
  });
}
</script>"""


def _esc(text: str) -> str:
    return _html.escape(text, quote=True)


def _shorten(value: str, head: int = 8, tail: int = 6) -> str:
    return value if len(value) <= head + tail + 1 else f"{value[:head]}…{value[-tail:]}"


def short_address(address: str) -> str:
    """0x90F79b…b906: enough to tell entries apart."""
    return address if len(address) <= 14 else f"{address[:8]}…{address[-4:]}"


def copy_block(rows, *, compact: bool = False, mask: bool = False) -> None:
    """Renders (label, value) rows, each with a Copy button for the FULL value.
    mask=True shows dots; compact=True shows head…tail, full value on hover.
    An empty label omits the label line."""
    rows = list(rows)
    parts = [_ASSETS]
    for label, value in rows:
        label_html = f'<span class="zk-copy-label">{_esc(label)}</span>' if label else ""
        if mask:
            shown, css, title = _MASK, "zk-copy-value zk-masked", ' title="Hidden: use Copy"'
        elif compact:
            shown = _shorten(value)
            css = "zk-copy-value zk-compact"
            title = f' title="{_esc(value)}"' if shown != value else ""
        else:
            shown, css, title = value, "zk-copy-value", ""
        parts.append(
            f'<div class="zk-copy">{label_html}<div class="zk-copy-row">'
            f'<span class="{css}"{title}>{_esc(shown)}</span>'
            f'<button type="button" class="zk-copy-btn" aria-label="Copy {_esc(label or "value")}" '
            f'data-copy="{_esc(value)}">Copy</button></div></div>'
        )
    try:
        st.html("".join(parts), unsafe_allow_javascript=True)
    except TypeError:                                  # Streamlit too old for unsafe_allow_javascript
        for label, value in rows:
            if label:
                st.caption(label)
            st.code(value, language=None)
