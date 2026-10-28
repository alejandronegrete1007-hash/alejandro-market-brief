"""Header search: type a company name or a ticker anywhere in the app and jump to its analysis.

The list of names (every SEC registrant, common ETFs, the Mexican ADRs and big foreign names traded
over the counter) is sent to the browser once per session and searched there, so typing never
reloads the page. Press "/" to focus the box.
"""
from __future__ import annotations

import streamlit as st

import sources as src
from views.common import route

_JS = r"""
// The index lives on window: the component can be mounted again (new module instance) when pages change.
const norm = s => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^a-z0-9& ]/g, ' ').replace(/\s+/g, ' ').trim();
function load(text) {
  window.__ambIdx = text.split('\n').filter(Boolean).map(l => {
    const i = l.indexOf('|'); const s = l.slice(0, i), n = l.slice(i + 1);
    return [s, n, ' ' + norm(n)];
  });
}
function index() {
  if (!window.__ambIdx) { try { const c = sessionStorage.getItem('amb_idx_v1'); if (c) load(c); } catch (e) {} }
  return window.__ambIdx;
}
function find(raw) {
  const q = norm(raw), up = raw.trim().toUpperCase();
  const IDX = index();
  if (!q || !IDX) return [];
  const out = [];
  for (const [s, n, nn] of IDX) {
    let sc = -1;
    if (s === up) sc = 0;
    else if (s.startsWith(up) && up.length >= 1) sc = 1 + s.length / 10;
    else if (nn.startsWith(' ' + q)) sc = 2 + nn.length / 200;
    else if (q.length >= 2 && nn.includes(' ' + q)) sc = 3 + nn.length / 200;
    else if (q.length >= 3 && nn.includes(q)) sc = 4 + nn.length / 200;
    if (sc >= 0) out.push([sc, s, n]);
  }
  out.sort((a, b) => a[0] - b[0]);
  return out.slice(0, 8);
}
const esc = t => t.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  if (data && typeof data.index === 'string' && data.index.length) {
    load(data.index);
    try { sessionStorage.setItem('amb_idx_v1', data.index); } catch (e) {}
  }
  let root = parentElement.querySelector(':scope > .amb-search');
  if (root) return;
  root = document.createElement('div');
  root.className = 'amb-search';
  root.innerHTML = `<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M13 13l4 4"/></svg>
    <input type="text" placeholder="Search company or ticker" aria-label="Search a company or ticker" autocomplete="off" spellcheck="false">
    <kbd>/</kbd><ul role="listbox"></ul>`;
  parentElement.appendChild(root);
  const input = root.querySelector('input'), list = root.querySelector('ul');
  let items = [], active = 0;
  const close = () => { list.innerHTML = ''; root.classList.remove('open'); items = []; };
  const go = sym => { if (!sym) return; setTriggerValue('go', 't:' + sym); input.value = ''; close(); input.blur(); };
  const draw = () => {
    if (!items.length) {
      const up = input.value.trim().toUpperCase();
      list.innerHTML = input.value.trim() ? (/^[A-Z]{1,5}(\.[A-Z])?$/.test(up)
        ? `<li class="hint">Press Enter to open ${esc(up)}</li>` : '<li class="hint">No US-listed match</li>') : '';
      root.classList.toggle('open', !!input.value.trim());
      return;
    }
    list.innerHTML = items.map(([, s, n], i) =>
      `<li role="option" data-s="${esc(s)}" class="${i === active ? 'on' : ''}"><b>${esc(s)}</b><span>${esc(n)}</span></li>`).join('');
    root.classList.add('open');
  };
  input.addEventListener('input', () => { items = find(input.value); active = 0; draw(); });
  input.addEventListener('focus', () => { if (input.value) { items = find(input.value); draw(); } });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, items.length - 1); draw(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); draw(); }
    else if (e.key === 'Escape') { close(); input.blur(); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (items.length) go(items[active][1]);
      else { const up = input.value.trim().toUpperCase(); if (/^[A-Z]{1,5}(\.[A-Z])?$/.test(up)) go(up); }
    }
  });
  list.addEventListener('mousedown', e => { const li = e.target.closest('li[data-s]'); if (li) { e.preventDefault(); go(li.dataset.s); } });
  document.addEventListener('mousedown', e => { if (!root.contains(e.target)) close(); });
  document.addEventListener('keydown', e => {
    const tag = (document.activeElement && document.activeElement.tagName) || '';
    if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(tag)) { e.preventDefault(); input.focus(); }
  });
}
"""
_search = st.components.v2.component("amb_search", js=_JS, isolate_styles=False)


def render():
    """Draw the search box (fixed in the header on wide screens) and open the stock that was picked."""
    data = {}
    if not st.session_state.get("_search_index_sent"):
        try:
            data["index"] = src.search_index()
            st.session_state["_search_index_sent"] = True
        except Exception:
            pass
    r = _search(data=data, key="amb_search", on_go_change=lambda: None)
    route(getattr(r, "go", None))
