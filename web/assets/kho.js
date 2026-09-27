/* Kho dữ liệu: danh sách khách sạn đã cào, trang chi tiết đối soát và cào bù. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
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
    if (!response.ok) throw new Error(data.error || `Lỗi ${response.status}`);
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
    if (!silent) $('kho-body').innerHTML = '<tr><td colspan="7" class="empty">Đang đọc kho…</td></tr>';
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
      citySel.innerHTML = '<option value="">Tất cả thành phố</option>' + (tk.thanh_pho || [])
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
    if (!ban) return `<span class="chip none">— chưa cào ${lang.toUpperCase()}</span>`;
    if (!ban.doc_duoc) return '<span class="chip bad">raw lỗi</span>';
    // Raw đủ packet mà trống → Trip.com không có phần đó (xám, không phải lỗi cào).
    const NONE_TITLE = 'Trip.com không cung cấp phần này cho khách sạn (đã cào đủ, không phải cào thiếu)';
    const c = (ok, text, noneText) => (ok
      ? `<span class="chip ok">${text}</span>`
      : ban.hoan_chinh
        ? `<span class="chip none" title="${NONE_TITLE}">${noneText}</span>`
        : `<span class="chip bad" title="Raw chưa đủ packet — nên cào bù">${text}</span>`);
    return c(ban.co_mo_ta, ban.co_mo_ta ? '✓ mô tả' : '✗ mô tả', '— không có mô tả')
      + c(ban.so_chinh_sach > 0, `▤ ${ban.so_chinh_sach} CS`, '— không có CS')
      + c(ban.so_lan_can > 0, `⌖ ${ban.so_lan_can} LC`, '— không có LC')
      + (ban.hoan_chinh ? '' : '<span class="chip warn">thiếu packet</span>')
      + (ban.thay_doi ? `<span class="chip info" title="${esc(Object.entries(ban.thay_doi.tom_tat || {}).map(([k, v]) => `${k}: ${v}`).join(', '))}">Δ ${ban.thay_doi.so_muc} thay đổi</span>` : '');
  }

  function render() {
    const body = $('kho-body');
    const rows = filtered.slice(0, shown);
    if (!loaded) return;
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty">Không có khách sạn nào khớp bộ lọc.</td></tr>';
    } else {
      body.innerHTML = rows.map((h) => `
        <tr data-id="${h.trip_hotel_id}" class="${h.thieu.some((f) => !f.startsWith('khong_') && f !== 'thieu_ngon_ngu') ? 'has-missing' : ''}">
          <td class="col-check"><input type="checkbox" data-check="${h.trip_hotel_id}" ${selected.has(h.trip_hotel_id) ? 'checked' : ''}></td>
          <td class="col-name"><button type="button" class="link-button" data-open="${h.trip_hotel_id}" title="${esc(h.ten)}">${esc(h.ten)}</button><small>ID ${h.trip_hotel_id}${h.ten_en && h.ten_vi && h.ten_en !== h.ten_vi ? ` · ${esc(h.ten_en)}` : ''}</small></td>
          <td>${esc(h.city_name || '—')}</td>
          <td class="col-chips">${chip(h.ngon_ngu.vi, 'vi')}</td>
          <td class="col-chips">${chip(h.ngon_ngu.en, 'en')}</td>
          <td class="col-time" title="${esc(dateTime(h.cap_nhat))}">${esc(dateTime(h.cap_nhat).replace(/\/\d{4}$/, ''))}</td>
          <td><button type="button" class="button mini ghost" data-open="${h.trip_hotel_id}">Xem</button></td>
        </tr>`).join('');
    }
    $('kho-visible').textContent = num(filtered.length);
    $('kho-more').hidden = filtered.length <= shown;
    $('kho-more').textContent = `Hiện thêm (${num(Math.max(0, filtered.length - shown))} còn lại)`;
    $('kho-check-all').checked = filtered.length > 0 && filtered.every((h) => selected.has(h.trip_hotel_id));
    updateSelection();
  }

  function updateSelection() {
    const n = selected.size;
    $('kho-cao-bu-count').textContent = num(n);
    $('kho-cao-bu').disabled = n === 0 || langsForCaoBu().length === 0;
    $('kho-selected-note').textContent = n
      ? `Đã chọn ${num(n)} khách sạn · cào bù ${langsForCaoBu().map((l) => l.toUpperCase()).join(' + ') || '(chọn ngôn ngữ)'}`
      : 'Tick chọn khách sạn cần cào lại, hoặc dùng bộ lọc "Thiếu…" rồi "Chọn tất cả".';
  }

  async function startCaoBu(ids) {
    const langs = langsForCaoBu();
    if (!ids.length) return toast('Chưa chọn khách sạn nào.', 'error');
    if (!langs.length) return toast('Hãy chọn ngôn ngữ cần cào bù.', 'error');
    try {
      await api('/api/kho/cao-bu', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, ngon_ngu: langs }),
      });
      toast(`Đang cào bù ${num(ids.length)} khách sạn (${langs.map((l) => l.toUpperCase()).join(', ')}). Theo dõi ở tab Cào dữ liệu.`);
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
      b.title = b.disabled ? 'Chưa cào ngôn ngữ này' : '';
    });
    document.querySelector('.kho-card').hidden = true;
    $('kho-detail').hidden = false;
    $('detail-body').innerHTML = '<p class="empty">Đang đọc raw…</p>';
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
    if (!d.mo_ta) missing.push('mô tả');
    if (!d.chinh_sach.length) missing.push('chính sách');
    if (!d.lan_can.length) missing.push('lân cận');
    const missingLabel = missing.length
      ? (d.hoan_chinh ? `Trip.com không có: ${missing.join(', ')}` : `Thiếu: ${missing.join(', ')}`)
      : 'Đủ 3 phần';
    const summary = `
      <div class="detail-head">
        <div class="grow">
          <p class="eyebrow">KHÁCH SẠN · ID ${esc(d.trip_hotel_id)} · ${esc(d.locale)}/${esc(d.currency)}</p>
          <h2>${esc(d.ten || '(chưa có tên)')}</h2>
          ${d.ten_dia_phuong && d.ten_dia_phuong !== d.ten ? `<p class="detail-sub">${esc(d.ten_dia_phuong)}</p>` : ''}
          <p class="detail-sub">${esc(d.dia_chi || 'Chưa có địa chỉ')}${d.city ? ` · ${esc(d.city.city_name)}${d.city.country_name ? `, ${esc(d.city.country_name)}` : ''}` : ''}</p>
        </div>
        <div class="detail-meta">
          <span class="badge ${!missing.length ? 'success' : d.hoan_chinh ? '' : 'warning'}">${missingLabel}</span>
          ${d.hoan_chinh ? '' : '<span class="badge failed">Raw thiếu packet</span>'}
          <small>Cào lúc ${dateTime(d.cap_nhat)}${d.so_phong ? ` · ${num(d.so_phong)} phòng` : ''}</small>
          <small class="mono" title="${esc(d.raw_path)}">${esc(d.raw_path.split(/[\\/]/).slice(-3).join('/'))}</small>
        </div>
      </div>
      <nav class="detail-jump">
        <a href="#dt-mo-ta">Mô tả</a><a href="#dt-chinh-sach">Chính sách (${d.chinh_sach.length})</a><a href="#dt-lan-can">Lân cận (${d.lan_can.length})</a>
      </nav>`;

    const moTa = `<section class="detail-block" id="dt-mo-ta">
        <div class="detail-block-title"><span>type = DESCRIPTION</span><h3>Mô tả khách sạn</h3></div>
        ${d.mo_ta
          ? `<div class="detail-text">${esc(d.mo_ta).split(/\n{2,}|\r?\n/).filter(Boolean).map((p) => `<p>${p}</p>`).join('')}</div><small class="muted">${num(d.mo_ta.length)} ký tự</small>`
          : (d.hoan_chinh
            ? '<div class="detail-none">Trip.com không có mô tả cho khách sạn này (đã cào đủ packet — không phải cào thiếu).</div>'
            : '<div class="detail-empty">Chưa crawl được phần mô tả (raw chưa đủ packet — nên cào bù).</div>')}
      </section>`;

    const POLICY_ICON = {
      checkInAndOut: '🕒', childPolicy: '🧒', cribAndExtraBed: '🛏', breakfast: '🍳', deposit: '💳',
      pet: '🐾', serviceAnimal: '🦮', ageLimit: '🔞', credit: '💵', guestLimit: '👥', quiteTime: '🔕',
      cancellation: '↩', parking: '🅿', smoking: '🚭',
    };
    const policyLines = (dong) => {
      // Dòng có nhãn → "Nhãn: nội dung", các dòng nhãn liên tiếp xếp cùng hàng (như Nhận/Trả phòng).
      // Chuỗi ≥2 dòng có nhãn VÀ in đậm liên tiếp (bảng giá bữa sáng…) → bảng như Trip.com.
      const out = [];
      let run = [];
      const flush = () => {
        if (!run.length) return;
        if (run.length >= 2 && run.every((l) => l.dam)) {
          out.push(`<table class="pl-table">${run.map((l) => `<tr><td>${esc(l.nhan.replace(/:\s*$/, ''))}</td><td class="${/^(miễn phí|free)$/i.test(l.noi_dung.trim()) ? 'free' : ''}">${esc(l.noi_dung)}</td></tr>`).join('')}</table>`);
        } else {
          out.push(`<div class="pl-row">${run.map((l) => `<span class="pl-pair"><span class="pl-label">${esc(l.nhan.replace(/:\s*$/, ''))}:</span> <b>${esc(l.noi_dung)}</b></span>`).join('')}</div>`);
        }
        run = [];
      };
      dong.forEach((l) => {
        if (l.nhan) {
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
        <div class="detail-block-title"><span>type = POLICY</span><h3>Chính sách</h3><small>${d.chinh_sach.length} mục</small></div>
        ${d.chinh_sach.length ? `<div class="policy-list">${d.chinh_sach.map((s) => `
          <div class="policy-row">
            <div class="policy-name"><span class="policy-icon">${POLICY_ICON[s.ma] || '▸'}</span><h4>${esc(s.tieu_de)}</h4><code>${esc(s.ma)}</code></div>
            <div class="policy-body">${policyLines(s.dong)}</div>
          </div>`).join('')}</div>`
          : (d.hoan_chinh
            ? '<div class="detail-none">Trip.com không có chính sách cho khách sạn này (đã cào đủ packet).</div>'
            : '<div class="detail-empty">Chưa crawl được chính sách (raw chưa đủ packet — nên cào bù).</div>')}
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
        <div class="detail-block-title"><span>type = SURROUNDING</span><h3>Địa điểm lân cận</h3><small>${num(d.lan_can.length)} địa điểm · ${groups.size} nhóm</small></div>
        ${groups.size ? `<div class="nearby-columns">${[...groups.values()].sort((a, b) => a.ma - b.ma).map((g) => `
          <div class="nearby-group">
            <h4><span class="nearby-icon">${GROUP_ICON[g.ma] || '📌'}</span>${esc(g.ten || 'Nhóm ' + g.ma)}<small>${String(g.ma).padStart(2, '0')} · ${g.items.length}</small></h4>
            <ul class="nearby-list">${g.items.map((p) => `<li title="${esc(p.khoang_cach_chu || '')}">
              <span class="nb-name">${g.ma === 2 && (p.nhan_loai || p.loai) ? `<span class="nb-kind">${esc(p.nhan_loai || p.loai)}:</span> ` : ''}${esc(p.ten)}</span>
              <span class="nb-dist">${esc(km(p))}</span>
            </li>`).join('')}</ul>
          </div>`).join('')}</div>`
          : (d.hoan_chinh
            ? '<div class="detail-none">Trip.com không có địa điểm lân cận cho khách sạn này (đã cào đủ packet).</div>'
            : '<div class="detail-empty">Chưa crawl được địa điểm lân cận (raw chưa đủ packet — nên cào bù).</div>')}
      </section>`;

    const KIND = { them: 'thêm', xoa: 'bỏ', sua: 'đổi' };
    const thayDoi = d.thay_doi && d.thay_doi.so_muc
      ? `<section class="detail-block changes" id="dt-thay-doi">
          <div class="detail-block-title"><span>SO VỚI LẦN CÀO TRƯỚC</span><h3>Thay đổi</h3><small>${d.thay_doi.so_muc} mục · lúc ${dateTime(d.thay_doi.luc)}</small></div>
          <table class="changes-table"><thead><tr><th>Phần</th><th>Mục</th><th>Trước</th><th>Sau</th></tr></thead><tbody>
          ${d.thay_doi.muc.map((m) => `<tr class="ch-${m.loai}"><td>${esc(m.phan)}</td><td>${esc(m.khoa)}<small>${KIND[m.loai] || ''}</small></td><td class="before">${esc(m.truoc) || '<i>—</i>'}</td><td class="after">${esc(m.sau) || '<i>—</i>'}</td></tr>`).join('')}
          </tbody></table>
        </section>`
      : '';
    const issues = d.loi_boc && d.loi_boc.length
      ? `<details class="detail-issues"><summary>${d.loi_boc.length} cảnh báo khi bóc raw</summary><ul>${d.loi_boc.map((i) => `<li>${esc(i)}</li>`).join('')}</ul></details>` : '';

    $('detail-body').innerHTML = summary + thayDoi + moTa + chinhSach + lanCan + issues;
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
    // Raw vừa đổi (cào mới hoặc cào bù) → làm mới kho, giữ trang chi tiết đang xem.
    if (loaded) load(true).then(() => { if (currentHotel) openDetail(currentHotel.id, currentHotel.lang); });
  });
  // Đếm cho nav ngay cả khi chưa mở tab.
  api('/api/kho/danh-sach').then((d) => { $('nav-kho-count').textContent = num((d.thong_ke || {}).tong); }).catch(() => {});
})();
