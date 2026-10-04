/* Giao diện đa ngôn ngữ theo khoá.
   - Chữ nằm trong /locales/<lang>.json (vi, en). Đổi chữ = sửa JSON, không sửa code.
   - Ghi đè riêng từng máy: <thư mục dữ liệu>/locales/override.json → {"vi": {...}, "en": {...}}
     (server trả về qua /api/locales/override).
   - HTML tĩnh: data-i18n="khoá" (textContent), data-i18n-html="khoá" (innerHTML),
     data-i18n-placeholder / data-i18n-title / data-i18n-aria="khoá".
   - JS: window.t('khoá', {n: 5}) → chuỗi đã điền {n}. Khoá không có → trả về chính khoá
     (dễ thấy để bổ sung).
   - crawl.js / kho.js / combo.js chờ window.I18N.ready rồi mới chạy. */
(() => {
  'use strict';

  const SUPPORTED = ['vi', 'en'];
  let lang = 'en';
  try { lang = localStorage.getItem('ui-lang') || 'en'; } catch (_) { /* không có localStorage */ }
  if (!SUPPORTED.includes(lang)) lang = 'en';

  let dict = {};
  const missing = new Set();

  function format(text, params) {
    if (!params) return text;
    return text.replace(/\{(\w+)\}/g, (m, k) => (params[k] === undefined || params[k] === null ? m : String(params[k])));
  }

  function t(key, params) {
    const text = dict[key];
    if (text === undefined) {
      if (!missing.has(key)) { missing.add(key); console.warn(`[i18n] thiếu khoá "${key}" cho ${lang}`); }
      return format(key, params);
    }
    return format(text, params);
  }

  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    scope.querySelectorAll('[data-i18n-html]').forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    scope.querySelectorAll('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    scope.querySelectorAll('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    scope.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  }

  async function fetchJson(url) {
    try {
      const r = await fetch(url, { cache: 'no-cache' });
      if (!r.ok) return {};
      return await r.json();
    } catch (_) { return {}; }
  }

  const ready = (async () => {
    const [base, override] = await Promise.all([
      fetchJson(`/locales/${lang}.json`),
      fetchJson('/api/locales/override'),
    ]);
    dict = { ...base, ...((override && override[lang]) || {}) };
    delete dict._meta;
    if (document.readyState === 'loading') {
      await new Promise((resolve) => document.addEventListener('DOMContentLoaded', resolve, { once: true }));
    }
    document.documentElement.lang = lang;
    document.title = t('app.title');
    apply(document);
    document.querySelectorAll('[data-ui-lang]').forEach((b) => {
      b.classList.toggle('active', b.dataset.uiLang === lang);
      b.addEventListener('click', () => window.I18N.set(b.dataset.uiLang));
    });
    // Phần tử thêm sau này có data-i18n cũng được dịch (vd. template sinh bằng JS).
    new MutationObserver((records) => {
      for (const r of records) {
        r.addedNodes.forEach((n) => { if (n.nodeType === Node.ELEMENT_NODE) apply(n); });
      }
    }).observe(document.body, { childList: true, subtree: true });
    return dict;
  })();

  window.t = t;
  window.I18N = {
    get lang() { return lang; },
    t,
    apply,
    ready,
    keys: () => Object.keys(dict),
    set(next) {
      if (next === lang || !SUPPORTED.includes(next)) return;
      try { localStorage.setItem('ui-lang', next); } catch (_) { /* bỏ qua */ }
      window.location.reload();
    },
  };
})();
