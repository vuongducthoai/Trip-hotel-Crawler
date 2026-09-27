/* Ô chọn gõ-tìm: bọc một <select> có sẵn thành input + danh sách gợi ý.
   Select gốc vẫn giữ giá trị nên code cũ (đọc .value, nghe 'change') không đổi. */
(() => {
  'use strict';

  const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase().trim();
  const initials = (s) => norm(s).split(/[\s\-–()/,.]+/).filter(Boolean).map((w) => w[0]).join('');

  /** Điểm khớp: 0 = không, cao hơn = tốt hơn. */
  function score(label, extra, q) {
    if (!q) return 1;
    const l = norm(label);
    const e = norm(extra);
    if (l === q) return 100;
    if (l.startsWith(q)) return 90;
    if (initials(label).startsWith(q)) return 80;           // "hk" → Hong Kong, "hcm" → Ho Chi Minh
    if (l.split(/[\s\-–()/,.]+/).some((w) => w.startsWith(q))) return 70;
    if (l.includes(q)) return 60;
    if (e && (e.startsWith(q) || e.includes(q))) return 40;  // khớp quốc gia
    return 0;
  }

  /**
   * @param select  <select> gốc
   * @param opts.items  () => [{value,label,extra?,pick?}] — nguồn gợi ý (mặc định: option của select)
   * @param opts.placeholder
   */
  window.makeCombo = function makeCombo(select, opts = {}) {
    const wrap = document.createElement('div');
    wrap.className = 'combo';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'combo-input';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = opts.placeholder || 'Gõ để tìm…';
    const caret = document.createElement('span');
    caret.className = 'combo-caret';
    caret.textContent = '⌄';
    const list = document.createElement('div');
    list.className = 'combo-list';
    list.hidden = true;
    select.parentNode.insertBefore(wrap, select);
    wrap.append(input, caret, list);
    select.classList.add('combo-hidden-select');
    select.tabIndex = -1;

    let items = [];
    let active = -1;
    let open = false;

    const source = () => (opts.items ? opts.items() : [...select.options].map((o) => ({ value: o.value, label: o.textContent })));
    const selectedLabel = () => {
      const o = select.options[select.selectedIndex];
      return o ? o.textContent : '';
    };
    const syncFromSelect = () => {
      if (document.activeElement !== input) input.value = selectedLabel();
      input.disabled = select.disabled;
      wrap.classList.toggle('disabled', select.disabled);
    };

    function render(q) {
      let all = source();
      // Chưa gõ gì: chỉ hiện mục "own" (vd. thành phố thuộc quốc gia đang chọn) nếu có.
      if (!q && all.some((it) => it.own)) all = all.filter((it) => it.own);
      items = all.map((it) => ({ ...it, s: score(it.label, it.extra, q) + (it.own ? 5 : 0) }))
        .filter((it) => it.s > (it.own ? 5 : 0))
        .sort((a, b) => b.s - a.s || a.label.localeCompare(b.label, 'vi'))
        .slice(0, 60);
      active = items.length ? 0 : -1;
      list.innerHTML = items.length
        ? items.map((it, i) => `<div class="combo-item${i === active ? ' active' : ''}" data-i="${i}">${escape(it.label)}${it.extra ? `<small>${escape(it.extra)}</small>` : ''}</div>`).join('')
        : '<div class="combo-empty">Không có kết quả.</div>';
      list.hidden = false;
      open = true;
    }
    const escape = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    function close() {
      list.hidden = true;
      open = false;
      syncFromSelect();
    }
    function pick(i) {
      const it = items[i];
      if (!it) return close();
      if (it.pick) {
        it.pick(it);
      } else if (select.value !== String(it.value)) {
        select.value = it.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      input.value = it.label;
      list.hidden = true;
      open = false;
      input.blur();
      syncFromSelect();
    }
    function highlight() {
      [...list.children].forEach((n, i) => n.classList.toggle('active', i === active));
      const node = list.children[active];
      if (node && node.scrollIntoView) node.scrollIntoView({ block: 'nearest' });
    }

    input.addEventListener('focus', () => { input.select(); render(''); });
    input.addEventListener('input', () => render(norm(input.value)));
    input.addEventListener('keydown', (e) => {
      if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) { render(norm(input.value)); e.preventDefault(); return; }
      if (e.key === 'ArrowDown') { active = Math.min(items.length - 1, active + 1); highlight(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { active = Math.max(0, active - 1); highlight(); e.preventDefault(); }
      else if (e.key === 'Enter') { pick(active); e.preventDefault(); }
      else if (e.key === 'Escape') { close(); input.blur(); }
    });
    list.addEventListener('mousedown', (e) => {
      const node = e.target.closest('.combo-item');
      if (node) { e.preventDefault(); pick(Number(node.dataset.i)); }
    });
    caret.addEventListener('mousedown', (e) => { e.preventDefault(); if (open) { close(); input.blur(); } else input.focus(); });
    input.addEventListener('blur', () => setTimeout(() => { if (open) close(); }, 120));
    select.addEventListener('change', syncFromSelect);
    new MutationObserver(syncFromSelect).observe(select, { childList: true, attributes: true });
    setInterval(syncFromSelect, 500);
    syncFromSelect();
    return { refresh: syncFromSelect };
  };
})();
