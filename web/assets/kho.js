/* Dữ liệu khách sạn: danh sách đã đồng bộ, trang chi tiết đối soát và đồng bộ bổ sung.
   Chữ hiển thị lấy qua t('khoá') từ /locales/<lang>.json. */
window.I18N.ready.then(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const t = window.t;
  const PAGE = 60;
  let all = [];            // toàn bộ khách sạn từ server
  let filtered = [];       // sau khi lọc
  let shown = PAGE;        // số dòng đang hiển thị
  let selected = new Set();
  let loaded = false;
  let currentHotel = null; // {id, lang}
  let toastTimer;

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    let data = {};
    try { data = await response.json(); } catch (_) { /* không có JSON */ }
    if (!response.ok) throw new Error(data.error || t('error.http', { status: response.status }));
    return data;
  }
  function toast(message, type = 'success') {
    clearTimeout(toastTimer);
    const node = $('toast');
    node.textContent = message;
    node.className = `toast show ${type}`;
    toastTimer = setTimeout(() => { node.className = 'toast'; }, 3500);
  }
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v) => Number(v || 0).toLocaleString('vi-VN');
  function taBadge(ta) {
    if (!ta || !ta.match_status) return `<span class="badge" title="${esc(t('ta.badgePendingTitle'))}">${esc(t('ta.badgePending'))}</span>`;
    if (ta.match_status === 'matched') {
      return `<span class="badge success" title="${esc(ta.tripadvisor_name || '')}">${esc(t('ta.badgeMatched', { id: ta.tripadvisor_location_id }))}${ta.rating ? ` · ${ta.rating}★` : ''}</span>`;
    }
    if (ta.match_status === 'review') {
      return `<span class="badge warning" title="${esc(t('ta.badgeReviewTitle', { name: ta.tripadvisor_name || '', m: ta.distance_m == null ? '?' : ta.distance_m }))}">${esc(t('ta.badgeReview', { id: ta.tripadvisor_location_id || '' }))}</span>`;
    }
    if (ta.match_status === 'error') return `<span class="badge failed" title="${esc(ta.last_error || '')}">${esc(t('ta.badgeError'))}</span>`;
    return `<span class="badge">${esc(t('ta.badgeNone'))}</span>`;
  }

  function dateTime(value) {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' });
  }
  function langsForCaoBu() {
    return [$('kho-lang-vi').checked ? 'vi' : null, $('kho-lang-en').checked ? 'en' : null].filter(Boolean);
  }

  /* ---------- Danh sách ---------- */
  async function load(silent = false) {
    if (!silent) $('kho-body').innerHTML = `<tr><td colspan="7" class="empty">${esc(t('data.loading'))}</td></tr>`;
    try {
      const data = await api('/api/kho/danh-sach');
      all = data.khach_san || [];
      loaded = true;
      const tk = data.thong_ke || {};
      $('kho-tong').textContent = num(tk.tong);
      $('kho-vi').textContent = num(tk.vi);
      $('kho-en').textContent = num(tk.en);
      $('kho-thieu').textContent = num(tk.thieu);
      $('nav-kho-count').textContent = num(tk.tong);
      const citySel = $('kho-city');
      const keep = citySel.value;
      citySel.innerHTML = `<option value="">${esc(t('data.allCities'))}</option>` + (tk.thanh_pho || [])
        .map((c) => `<option value="${c.city_id}">${esc(c.city_name)}${c.country_name ? ` (${esc(c.country_name)})` : ''} · ${num(c.so_khach_san)}</option>`).join('');
      citySel.value = keep;
      // Bỏ các lựa chọn không còn trong kho.
      const ids = new Set(all.map((h) => h.trip_hotel_id));
      selected = new Set([...selected].filter((id) => ids.has(id)));
      applyFilter();
    } catch (error) {
      $('kho-body').innerHTML = `<tr><td colspan="7" class="empty">${esc(error.message)}</td></tr>`;
    }
  }

  function matchFilter(h, key) {
    if (!key) return true;
    if (key === 'thieu') return h.thieu.some((f) => !f.startsWith('khong_') && f !== 'thieu_ngon_ngu');
    if (key === 'thieu_ngon_ngu') return h.thieu.includes('thieu_ngon_ngu');
    if (key === 'thay_doi') return ['vi', 'en'].some((l) => h.ngon_ngu[l] && h.ngon_ngu[l].thay_doi);
    if (key === 'khong_co') return h.thieu.some((f) => f.startsWith('khong_'));
    return h.thieu.some((f) => f.startsWith(`${key}_`));
  }

  function applyFilter() {
    const q = $('kho-search').value.trim().toLowerCase();
    const city = $('kho-city').value;
    const key = $('kho-filter').value;
    filtered = all.filter((h) => {
      if (city && String(h.city_id) !== city) return false;
      if (!matchFilter(h, key)) return false;
      if (!q) return true;
      return h.trip_hotel_id.includes(q)
        || (h.ten_vi || '').toLowerCase().includes(q)
        || (h.ten_en || '').toLowerCase().includes(q);
    });
    shown = PAGE;
    render();
  }

  function chip(ban, lang) {
    if (!ban) return `<span class="chip none">${esc(t('chip.noLang', { lang: lang.toUpperCase() }))}</span>`;
    if (!ban.doc_duoc) return `<span class="chip bad">${esc(t('chip.rawError'))}</span>`;
    // Bản ghi đủ packet mà trống → Trip.com không có phần đó (xám, không phải thiếu do đồng bộ).
    const c = (ok, text, noneText) => (ok
      ? `<span class="chip ok">${esc(text)}</span>`
      : ban.hoan_chinh
        ? `<span class="chip none" title="${esc(t('chip.noneTitle'))}">${esc(noneText)}</span>`
        : `<span class="chip bad" title="${esc(t('chip.incompleteTitle'))}">${esc(text)}</span>`);
    return c(ban.co_mo_ta, ban.co_mo_ta ? t('chip.descOk') : t('chip.descMissing'), t('chip.descNone'))
      + c(ban.so_chinh_sach > 0, t('chip.policy', { n: ban.so_chinh_sach }), t('chip.policyNone'))
      + c(ban.so_lan_can > 0, t('chip.nearby', { n: ban.so_lan_can }), t('chip.nearbyNone'))
      + (ban.hoan_chinh ? '' : `<span class="chip warn">${esc(t('chip.packet'))}</span>`)
      + (ban.thay_doi ? `<span class="chip info" title="${esc(Object.entries(ban.thay_doi.tom_tat || {}).map(([k, v]) => `${k}: ${v}`).join(', '))}">${esc(t('chip.changed', { n: ban.thay_doi.so_muc }))}</span>` : '');
  }

  function render() {
    const body = $('kho-body');
    const rows = filtered.slice(0, shown);
    if (!loaded) return;
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="7" class="empty">${esc(t('data.noMatch'))}</td></tr>`;
    } else {
      body.innerHTML = rows.map((h) => `
        <tr data-id="${h.trip_hotel_id}" class="${h.thieu.some((f) => !f.startsWith('khong_') && f !== 'thieu_ngon_ngu') ? 'has-missing' : ''}">
          <td class="col-check"><input type="checkbox" data-check="${h.trip_hotel_id}" ${selected.has(h.trip_hotel_id) ? 'checked' : ''}></td>
          <td class="col-name"><button type="button" class="link-button" data-open="${h.trip_hotel_id}" title="${esc(h.ten)}">${esc(h.ten)}</button><small>ID ${h.trip_hotel_id}${h.ten_en && h.ten_vi && h.ten_en !== h.ten_vi ? ` · ${esc(h.ten_en)}` : ''}</small></td>
          <td>${esc(h.city_name || '—')}</td>
          <td class="col-chips">${chip(h.ngon_ngu.vi, 'vi')}</td>
          <td class="col-chips">${chip(h.ngon_ngu.en, 'en')}</td>
          <td class="col-time" title="${esc(dateTime(h.cap_nhat))}">${esc(dateTime(h.cap_nhat).replace(/\/\d{4}$/, ''))}</td>
          <td><button type="button" class="button mini ghost" data-open="${h.trip_hotel_id}">${esc(t('data.view'))}</button></td>
        </tr>`).join('');
    }
    $('kho-visible').textContent = num(filtered.length);
    $('kho-more').hidden = filtered.length <= shown;
    $('kho-more').textContent = t('data.moreN', { n: num(Math.max(0, filtered.length - shown)) });
    $('kho-check-all').checked = filtered.length > 0 && filtered.every((h) => selected.has(h.trip_hotel_id));
    updateSelection();
  }

  function updateSelection() {
    const n = selected.size;
    $('kho-cao-bu-count').textContent = num(n);
    $('kho-cao-bu').disabled = n === 0 || langsForCaoBu().length === 0;
    $('kho-selected-note').textContent = n
      ? t('data.selected', { n: num(n), langs: langsForCaoBu().map((l) => l.toUpperCase()).join(' + ') || t('data.pickLang') })
      : t('data.selectHint');
  }

  async function startCaoBu(ids) {
    const langs = langsForCaoBu();
    if (!ids.length) return toast(t('data.noSelection'), 'error');
    if (!langs.length) return toast(t('data.needLang'), 'error');
    try {
      await api('/api/kho/cao-bu', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, ngon_ngu: langs }),
      });
      toast(t('data.fillStarted', { n: num(ids.length), langs: langs.map((l) => l.toUpperCase()).join(', ') }));
      selected.clear();
      render();
      if (window.crawlerSetView) window.crawlerSetView('crawl');
    } catch (error) { toast(error.message, 'error'); }
  }

  /* ---------- Chi tiết ---------- */
  async function openDetail(id, lang) {
    const h = all.find((x) => x.trip_hotel_id === id);
    if (!lang) lang = h && h.ngon_ngu.vi ? 'vi' : 'en';
    currentHotel = { id, lang };
    document.querySelectorAll('.lang-switch .tab-button').forEach((b) => {
      const own = b.dataset.lang === lang;
      b.classList.toggle('active', own);
      b.setAttribute('aria-selected', own ? 'true' : 'false');
      b.disabled = !(h && h.ngon_ngu[b.dataset.lang]);
      b.title = b.disabled ? t('detail.noLang') : '';
    });
    document.querySelector('.kho-card').hidden = true;
    $('kho-detail').hidden = false;
    $('detail-body').innerHTML = `<p class="empty">${esc(t('detail.loading'))}</p>`;
    window.scrollTo({ top: $('kho-detail').offsetTop - 80, behavior: 'smooth' });
    try {
      const d = await api(`/api/kho/khach-san/${id}?lang=${lang}`);
      $('detail-trip').href = d.trip_url;
      renderDetail(d);
    } catch (error) {
      $('detail-body').innerHTML = `<p class="empty">${esc(error.message)}</p>`;
    }
  }

  function renderDetail(d) {
    const missing = [];
    if (!d.mo_ta) missing.push(t('detail.desc'));
    if (!d.chinh_sach.length) missing.push(t('detail.policy'));
    if (!d.lan_can.length) missing.push(t('detail.nearby'));
    const missingLabel = missing.length
      ? (d.hoan_chinh ? t('detail.tripNone', { list: missing.join(', ') }) : t('detail.missing', { list: missing.join(', ') }))
      : t('detail.complete');
    const summary = `
      <div class="detail-head">
        <div class="grow">
          <p class="eyebrow">${esc(t('detail.eyebrow', { id: d.trip_hotel_id, market: `${d.locale}/${d.currency}` }))}</p>
          <h2>${esc(d.ten || t('detail.noName'))}</h2>
          ${d.ten_dia_phuong && d.ten_dia_phuong !== d.ten ? `<p class="detail-sub">${esc(d.ten_dia_phuong)}</p>` : ''}
          <p class="detail-sub">${esc(d.dia_chi || t('detail.noAddress'))}${d.city ? ` · ${esc(d.city.city_name)}${d.city.country_name ? `, ${esc(d.city.country_name)}` : ''}` : ''}</p>
        </div>
        <div class="detail-meta">
          <span class="badge ${!missing.length ? 'success' : d.hoan_chinh ? '' : 'warning'}">${esc(missingLabel)}</span>
          ${d.hoan_chinh ? '' : `<span class="badge failed">${esc(t('detail.rawIncomplete'))}</span>`}
          ${taBadge(d.tripadvisor)}
          <small>${esc(t('detail.syncedAt', { time: dateTime(d.cap_nhat) }))}${d.so_phong ? esc(t('detail.rooms', { n: num(d.so_phong) })) : ''}${d.toa_do && d.toa_do.lat != null ? ` · ${d.toa_do.lat}, ${d.toa_do.lng}` : ''}</small>
          <small class="mono" title="${esc(d.raw_path)}">${esc(d.raw_path.split(/[\\/]/).slice(-3).join('/'))}</small>
        </div>
      </div>
      <nav class="detail-jump">
        <a href="#dt-tripadvisor">${esc(t('detail.jumpTa'))}</a><a href="#dt-mo-ta">${esc(t('detail.jumpDesc'))}</a><a href="#dt-chinh-sach">${esc(t('detail.jumpPolicy', { n: d.chinh_sach.length }))}</a><a href="#dt-lan-can">${esc(t('detail.jumpNearby', { n: d.lan_can.length }))}</a>
      </nav>`;

    const ta = d.tripadvisor;
    const TA_STATUS = {
      matched: [t('ta.sMatched'), 'success'],
      review: [t('ta.sReview'), 'warning'],
      no_match: [t('ta.sNoMatch'), ''],
      error: [t('ta.sError'), 'failed'],
    };
    const taBlock = `<section class="detail-block ta-block" id="dt-tripadvisor">
        <div class="detail-block-title"><span>field = tripAdvisorId</span><h3>TripAdvisor</h3></div>
        ${!ta ? `<p class="muted">${esc(t('ta.notYet'))}</p>` : `
        <div class="ta-detail">
          <span class="badge ${(TA_STATUS[ta.match_status] || ['', ''])[1]}">${esc((TA_STATUS[ta.match_status] || [ta.match_status])[0])}</span>
          <table class="ta-table">
            <tr><th>${esc(t('ta.tripName'))}</th><td>${esc(ta.trip_name || d.ten || '')}</td></tr>
            <tr><th>${esc(t('ta.taName'))}</th><td>${esc(ta.tripadvisor_name || '—')}</td></tr>
            <tr><th>${esc(t('ta.taId'))}</th><td class="mono">${esc(ta.tripadvisor_location_id ?? '—')}</td></tr>
            <tr><th>${esc(t('ta.similarity'))}</th><td>${ta.name_similarity == null ? '—' : `${Math.round(ta.name_similarity * 100)}% <small class="muted">${esc(t('ta.similarityHint'))}</small>`}</td></tr>
            <tr><th>${esc(t('ta.distance'))}</th><td>${ta.distance_m == null ? '—' : `${num(ta.distance_m)} m <small class="muted">${esc(t('ta.distanceHint'))}</small>`}</td></tr>
            <tr><th>${esc(t('ta.rating'))}</th><td>${ta.rating ? `${ta.rating}★${ta.review_count ? ` · ${esc(t('ta.reviews', { n: num(ta.review_count) }))}` : ''}` : '—'}</td></tr>
            ${ta.last_error ? `<tr><th>${esc(t('ta.errorRow'))}</th><td class="mono">${esc(ta.last_error)}</td></tr>` : ''}
            <tr><th>${esc(t('ta.matchedAt'))}</th><td>${ta.searched_at ? dateTime(ta.searched_at) : '—'}</td></tr>
          </table>
          ${ta.tripadvisor_url ? `<a class="button secondary mini" href="${esc(ta.tripadvisor_url)}" target="_blank" rel="noopener">${esc(t('ta.openPage'))}</a>` : ''}
        </div>`}
      </section>`;
    const moTa = `<section class="detail-block" id="dt-mo-ta">
        <div class="detail-block-title"><span>type = DESCRIPTION</span><h3>${esc(t('detail.descTitle'))}</h3></div>
        ${d.mo_ta
          ? `<div class="detail-text">${esc(d.mo_ta).split(/\n{2,}|\r?\n/).filter(Boolean).map((p) => `<p>${p}</p>`).join('')}</div><small class="muted">${esc(t('detail.chars', { n: num(d.mo_ta.length) }))}</small>`
          : (d.hoan_chinh
            ? `<div class="detail-none">${esc(t('detail.descNone'))}</div>`
            : `<div class="detail-empty">${esc(t('detail.descMissing'))}</div>`)}
      </section>`;

    const POLICY_ICON = {
      checkInAndOut: '🕒', childPolicy: '🧒', cribAndExtraBed: '🛏', breakfast: '🍳', deposit: '💳',
      pet: '🐾', serviceAnimal: '🦮', ageLimit: '🔞', credit: '💵', guestLimit: '👥', quiteTime: '🔕',
      cancellation: '↩', parking: '🅿', smoking: '🚭',
    };
    const policyLines = (dong) => {
      // Dòng có nhãn → "Nhãn: nội dung", các dòng nhãn liên tiếp xếp cùng hàng (như Nhận/Trả phòng).
      // Dòng Trip.com trả trong "tab" (bảng giá bữa sáng…, cờ dam=true) → bảng như Trip.com,
      // kể cả khi bảng chỉ có 1 hàng (vd. chỉ "Người lớn").
      const out = [];
      let run = [];
      const flush = () => {
        if (!run.length) return;
        if (run.every((l) => l.dam)) {
          out.push(`<table class="pl-table">${run.map((l) => `<tr><td>${esc(l.nhan.replace(/:\s*$/, ''))}</td><td class="${/^(miễn phí|free)$/i.test(l.noi_dung.trim()) ? 'free' : ''}">${esc(l.noi_dung)}</td></tr>`).join('')}</table>`);
        } else {
          out.push(`<div class="pl-row">${run.map((l) => `<span class="pl-pair"><span class="pl-label">${esc(l.nhan.replace(/:\s*$/, ''))}:</span> <b>${esc(l.noi_dung)}</b></span>`).join('')}</div>`);
        }
        run = [];
      };
      dong.forEach((l) => {
        if (l.nhan) {
          if (run.length && Boolean(run[0].dam) !== Boolean(l.dam)) flush();
          run.push(l);
        } else {
          flush();
          out.push(`<p class="pl-text ${l.dam ? 'bold' : ''}">${esc(l.noi_dung)}</p>`);
        }
      });
      flush();
      return out.join('');
    };
    const chinhSach = `<section class="detail-block" id="dt-chinh-sach">
        <div class="detail-block-title"><span>type = POLICY</span><h3>${esc(t('detail.policyTitle'))}</h3><small>${esc(t('detail.items', { n: d.chinh_sach.length }))}</small></div>
        ${d.chinh_sach.length ? `<div class="policy-list">${d.chinh_sach.map((s) => `
          <div class="policy-row">
            <div class="policy-name"><span class="policy-icon">${POLICY_ICON[s.ma] || '▸'}</span><h4>${esc(s.tieu_de)}</h4><code>${esc(s.ma)}</code></div>
            <div class="policy-body">${policyLines(s.dong)}</div>
          </div>`).join('')}</div>`
          : (d.hoan_chinh
            ? `<div class="detail-none">${esc(t('detail.policyNone'))}</div>`
            : `<div class="detail-empty">${esc(t('detail.policyMissing'))}</div>`)}
      </section>`;

    const groups = new Map();
    d.lan_can.forEach((p) => {
      const key = `${String(p.ma_nhom).padStart(2, '0')}_${p.ten_nhom || ''}`;
      if (!groups.has(key)) groups.set(key, { ma: p.ma_nhom, ten: p.ten_nhom, items: [] });
      groups.get(key).items.push(p);
    });
    const GROUP_ICON = { 2: '🚆', 3: '📍', 4: '🍽', 5: '🛍', 6: '🏥', 7: '🏫' };
    const km = (p) => (p.khoang_cach_km != null ? (p.khoang_cach_km >= 1 ? `${p.khoang_cach_km.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}km` : `${Math.round(p.khoang_cach_km * 1000)}m`) : '—');
    const lanCan = `<section class="detail-block" id="dt-lan-can">
        <div class="detail-block-title"><span>type = SURROUNDING</span><h3>${esc(t('detail.nearbyTitle'))}</h3><small>${esc(t('detail.nearbyCount', { n: num(d.lan_can.length), g: groups.size }))}</small></div>
        ${groups.size ? `<div class="nearby-columns">${[...groups.values()].sort((a, b) => a.ma - b.ma).map((g) => `
          <div class="nearby-group">
            <h4><span class="nearby-icon">${GROUP_ICON[g.ma] || '📌'}</span>${esc(g.ten || t('detail.group', { n: g.ma }))}<small>${String(g.ma).padStart(2, '0')} · ${g.items.length}</small></h4>
            <ul class="nearby-list">${g.items.map((p) => `<li title="${esc(p.khoang_cach_chu || '')}">
              <span class="nb-name">${g.ma === 2 && (p.nhan_loai || p.loai) ? `<span class="nb-kind">${esc(p.nhan_loai || p.loai)}:</span> ` : ''}${esc(p.ten)}</span>
              <span class="nb-dist">${esc(km(p))}</span>
            </li>`).join('')}</ul>
          </div>`).join('')}</div>`
          : (d.hoan_chinh
            ? `<div class="detail-none">${esc(t('detail.nearbyNone'))}</div>`
            : `<div class="detail-empty">${esc(t('detail.nearbyMissing'))}</div>`)}
      </section>`;

    const KIND = { them: t('detail.kAdd'), xoa: t('detail.kRemove'), sua: t('detail.kChange') };
    const thayDoi = d.thay_doi && d.thay_doi.so_muc
      ? `<section class="detail-block changes" id="dt-thay-doi">
          <div class="detail-block-title"><span>${esc(t('detail.changesKicker'))}</span><h3>${esc(t('detail.changes'))}</h3><small>${esc(t('detail.changesCount', { n: d.thay_doi.so_muc, time: dateTime(d.thay_doi.luc) }))}</small></div>
          <table class="changes-table"><thead><tr><th>${esc(t('detail.thPart'))}</th><th>${esc(t('detail.thItem'))}</th><th>${esc(t('detail.thBefore'))}</th><th>${esc(t('detail.thAfter'))}</th></tr></thead><tbody>
          ${d.thay_doi.muc.map((m) => `<tr class="ch-${m.loai}"><td>${esc(m.phan)}</td><td>${esc(m.khoa)}<small>${KIND[m.loai] || ''}</small></td><td class="before">${esc(m.truoc) || '<i>—</i>'}</td><td class="after">${esc(m.sau) || '<i>—</i>'}</td></tr>`).join('')}
          </tbody></table>
        </section>`
      : '';
    const issues = d.loi_boc && d.loi_boc.length
      ? `<details class="detail-issues"><summary>${esc(t('detail.issues', { n: d.loi_boc.length }))}</summary><ul>${d.loi_boc.map((i) => `<li>${esc(i)}</li>`).join('')}</ul></details>` : '';

    $('detail-body').innerHTML = summary + thayDoi + taBlock + moTa + chinhSach + lanCan + issues;
  }

  /* ---------- Sự kiện ---------- */
  $('kho-search').addEventListener('input', applyFilter);
  $('kho-city').addEventListener('change', applyFilter);
  $('kho-filter').addEventListener('change', applyFilter);
  $('kho-lang-vi').addEventListener('change', updateSelection);
  $('kho-lang-en').addEventListener('change', updateSelection);
  $('kho-reload').addEventListener('click', () => load());
  $('kho-more').addEventListener('click', () => { shown += PAGE; render(); });
  $('kho-check-all').addEventListener('change', (e) => {
    filtered.forEach((h) => (e.target.checked ? selected.add(h.trip_hotel_id) : selected.delete(h.trip_hotel_id)));
    render();
  });
  $('kho-body').addEventListener('change', (e) => {
    const id = e.target.dataset && e.target.dataset.check;
    if (!id) return;
    if (e.target.checked) selected.add(id); else selected.delete(id);
    $('kho-check-all').checked = filtered.length > 0 && filtered.every((h) => selected.has(h.trip_hotel_id));
    updateSelection();
  });
  $('kho-body').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-open]');
    if (btn) openDetail(btn.dataset.open);
  });
  $('kho-cao-bu').addEventListener('click', () => startCaoBu([...selected]));
  $('detail-back').addEventListener('click', () => {
    $('kho-detail').hidden = true;
    document.querySelector('.kho-card').hidden = false;
    currentHotel = null;
    window.scrollTo({ top: document.querySelector('.kho-card').offsetTop - 80, behavior: 'smooth' });
  });
  $('detail-cao-bu').addEventListener('click', () => { if (currentHotel) startCaoBu([currentHotel.id]); });
  document.querySelectorAll('.lang-switch .tab-button').forEach((b) => b.addEventListener('click', () => {
    if (currentHotel && !b.disabled) openDetail(currentHotel.id, b.dataset.lang);
  }));

  document.addEventListener('view-changed', (e) => {
    if (e.detail === 'kho' && !loaded) load();
  });
  document.addEventListener('job-finished', () => {
    // Raw vừa đổi (crawl mới hoặc crawl bù) → làm mới kho, giữ trang chi tiết đang xem.
    if (loaded) load(true).then(() => { if (currentHotel) openDetail(currentHotel.id, currentHotel.lang); });
  });
  // Đếm cho nav ngay cả khi chưa mở tab.
  api('/api/kho/danh-sach').then((d) => { $('nav-kho-count').textContent = num((d.thong_ke || {}).tong); }).catch(() => {});
});
