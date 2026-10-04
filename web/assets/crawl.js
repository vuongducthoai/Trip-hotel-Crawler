/* Dashboard một trang: đồng bộ metadata, theo dõi, lịch sử và xuất dữ liệu.
   Mọi chữ hiển thị lấy qua t('khoá') từ /locales/<lang>.json. */
window.I18N.ready.then(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const t = window.t;
  const fmtN = (v) => Number(v || 0).toLocaleString('vi-VN');
  let timer;
  let toastTimer;
  let cityTimer;
  let jobWasRunning = false;
  let continueMode = false;
  let catalogData = { countries: [], catalog: {} };
  let activeTab = 'destination';

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    let data = {};
    try { data = await response.json(); } catch (_) { /* Phản hồi không có JSON. */ }
    if (!response.ok) throw new Error(data.error || t('error.http', { status: response.status }));
    return data;
  }

  function post(path, body = {}) {
    return api(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  function toast(message, type = 'success') {
    clearTimeout(toastTimer);
    const node = $('toast');
    node.textContent = message;
    node.className = `toast show ${type}`;
    toastTimer = setTimeout(() => { node.className = 'toast'; }, 3500);
  }

  function languages() {
    return [$('lang-vi').checked ? 'vi' : null, $('lang-en').checked ? 'en' : null].filter(Boolean);
  }

  function saveForm() {
    localStorage.setItem('crawler-form', JSON.stringify({
      url: $('url').value, amount: $('amount').dataset.saved || $('amount').value,
      vi: $('lang-vi').checked, en: $('lang-en').checked,
    }));
  }

  function restoreForm() {
    try {
      const value = JSON.parse(localStorage.getItem('crawler-form') || '{}');
      if (value.url) $('url').value = value.url;
      if (value.amount) $('amount').value = value.amount;
      if (typeof value.vi === 'boolean') $('lang-vi').checked = value.vi;
      if (typeof value.en === 'boolean') $('lang-en').checked = value.en;
    } catch (_) { /* Dữ liệu cũ không hợp lệ thì dùng mặc định. */ }
  }

  function scheduleCityStats() {
    clearTimeout(cityTimer);
    cityTimer = setTimeout(refreshCityStats, 650);
  }

  function setContinueMode(enabled) {
    continueMode = Boolean(enabled);
    $('amount-label').textContent = continueMode ? t('amount.more') : t('amount.target');
    if (activeTab === 'ids') return;
    $('crawl-label').textContent = queueCities.size ? t('action.syncCities', { n: queueCities.size }) : (continueMode ? t('action.syncMore') : t('action.sync'));
    $('cancel-resume').hidden = !continueMode;
    $('resume-note').textContent = continueMode ? t('city.resumeOn') : t('city.resumeNote');
    scheduleCityStats();
  }

  function setTab(tabName) {
    activeTab = tabName;
    const tabs = { destination: 'tab-destination', 'custom-url': 'tab-custom-url', ids: 'tab-ids' };
    const panes = { destination: 'pane-destination', 'custom-url': 'pane-custom-url', ids: 'pane-ids' };
    Object.entries(tabs).forEach(([name, id]) => {
      const on = name === tabName;
      $(id).classList.toggle('active', on);
      $(id).setAttribute('aria-selected', on ? 'true' : 'false');
      $(panes[name]).hidden = !on;
    });
    const isIds = tabName === 'ids';
    document.querySelector('.queue-box').hidden = isIds;   // hàng đợi chỉ cho thành phố
    $('amount').disabled = isIds;                          // số lượng = số ID trong danh sách
    $('crawl').disabled = isIds && !idsSelected().length;
    if (isIds) {
      $('amount').dataset.saved = $('amount').dataset.saved || $('amount').value;
      $('amount-label').textContent = t('amount.list');
      $('amount').value = idsState.ids.length || '';
      $('city-status').hidden = true;
      if (idsState.ids.length) idsUpdateSummary(); else $('crawl-label').textContent = t('action.syncList');
    } else {
      if ($('amount').dataset.saved) { $('amount').value = $('amount').dataset.saved; delete $('amount').dataset.saved; }
      $('amount-label').textContent = continueMode ? t('amount.more') : t('amount.target');
      renderQueueChips();
    }
    scheduleCityStats();
  }

  function populateCitiesForCountry(countryName, selectCityId = null) {
    const citySelect = $('select-city');
    citySelect.innerHTML = '';
    const cities = (catalogData.catalog && catalogData.catalog[countryName]) || [];
    if (!cities.length) {
      citySelect.disabled = true;
      return;
    }
    citySelect.disabled = false;
    cities.forEach((city) => {
      const opt = document.createElement('option');
      opt.value = city.city_id;
      const tagStr = (city.tags && city.tags.length) ? ` [${city.tags.join(' ')}]` : '';
      opt.textContent = `${city.city_name}${tagStr}`;
      if (city.tags && city.tags.length) {
        opt.dataset.tags = JSON.stringify(city.tags);
      }
      if (selectCityId && Number(city.city_id) === Number(selectCityId)) {
        opt.selected = true;
      }
      citySelect.appendChild(opt);
    });
  }

  function selectDestinationByCityId(cityId) {
    if (!catalogData.catalog) return false;
    for (const [country, cities] of Object.entries(catalogData.catalog)) {
      const found = cities.find((c) => Number(c.city_id) === Number(cityId));
      if (found) {
        $('select-country').value = country;
        populateCitiesForCountry(country, cityId);
        return true;
      }
    }
    return false;
  }

  async function loadDestinations() {
    try {
      catalogData = await api('/api/destinations');
      const countrySelect = $('select-country');
      countrySelect.innerHTML = '';
      (catalogData.countries || []).forEach((country) => {
        const opt = document.createElement('option');
        opt.value = country;
        const cTags = (catalogData.country_tags && catalogData.country_tags[country]) || [];
        const tagStr = cTags.length ? ` [${cTags.join(' ')}]` : '';
        opt.textContent = `${country}${tagStr}`;
        if (cTags.length) {
          opt.dataset.tags = JSON.stringify(cTags);
        }
        countrySelect.appendChild(opt);
      });
      if (catalogData.countries && catalogData.countries.length) {
        const totalCities = Object.values(catalogData.catalog || {}).reduce((acc, list) => acc + list.length, 0);
        $('tab-destination').textContent = t('setup.tabDestination', { n: fmtN(totalCities) });
        $('country-label').textContent = t('setup.country', { n: catalogData.countries.length });
        $('setup-subtitle').textContent = t('setup.subtitle', { n: fmtN(totalCities) });
        const defaultCountry = catalogData.countries.includes('Thailand') ? 'Thailand' : catalogData.countries[0];
        countrySelect.value = defaultCountry;
        populateCitiesForCountry(defaultCountry);
      }
      scheduleCityStats();
    } catch (err) {
      console.error('Không tải được danh mục điểm đến:', err);
    }
  }

  async function refreshCityStats() {
    const box = $('city-status');
    const previewUrlNode = $('destination-preview-url');
    let requestBody = {};
    if (activeTab === 'ids') { box.hidden = true; return; }
    if (activeTab === 'destination') {
      const city_id = Number($('select-city').value);
      if (!city_id) {
        box.hidden = true;
        if (previewUrlNode) previewUrlNode.textContent = '';
        return;
      }
      const locale = $('lang-vi').checked ? 'vi-VN' : 'en-US';
      const currency = $('lang-vi').checked ? 'VND' : 'USD';
      requestBody = { city_id, locale, currency };
    } else {
      const url = $('url').value.trim();
      if (!url || !url.includes('trip.com')) {
        box.hidden = true;
        return;
      }
      requestBody = { url };
    }

    box.hidden = false;
    box.classList.add('loading');
    $('city-status-title').textContent = t('city.checking');
    $('city-status-text').textContent = '';
    try {
      const endpoint = activeTab === 'destination' ? '/api/destinations/preview' : '/api/crawl/thong-ke';
      const data = await post(endpoint, requestBody);
      if (activeTab === 'destination' && data.url && previewUrlNode) {
        previewUrlNode.textContent = t('setup.previewUrl', { url: data.url });
      }
      const selected = languages();
      const labels = { vi: 'VI', en: 'EN' };
      const target = Math.max(1, Number($('amount').value) || 1);
      const parts = selected.map((lang) => {
        const item = data.languages[lang] || { total: 0, complete: 0, incomplete: 0 };
        const repair = item.incomplete ? t('city.repair', { n: item.incomplete }) : '';
        if (continueMode) {
          return t('city.statMore', { lang: labels[lang], complete: item.complete, target, total: item.complete + target, repair });
        }
        const remaining = Math.max(0, target - item.complete);
        return t('city.statTarget', { lang: labels[lang], complete: item.complete, remaining, target, repair });
      });
      const cityName = data.city_name || (data.place && data.place.city_name);
      const countryName = data.country_name || (data.place && data.place.country_name);
      const titleCountry = countryName ? ` (${countryName})` : '';
      $('city-status-title').textContent = t('city.canResume', { city: `${cityName}${titleCountry}` });
      $('city-status-text').textContent = parts.join('  |  ') || t('city.pickLang');
      box.classList.remove('loading');
    } catch (_) {
      box.hidden = true;
    }
  }

  /* ---------- Hàng đợi nhiều thành phố (phía client, trước khi gửi) ---------- */
  const queueCities = new Map();   // city_id -> {city_id, city_name, country}

  function cityLabel(cityId) {
    for (const [country, cities] of Object.entries(catalogData.catalog || {})) {
      const found = cities.find((c) => Number(c.city_id) === Number(cityId));
      if (found) return { city_id: Number(cityId), city_name: found.city_name, country };
    }
    return null;
  }

  function renderQueueChips() {
    const box = $('queue-list');
    if (!queueCities.size) {
      box.innerHTML = `<span class="muted">${esc(t('queue.empty'))}</span>`;
    } else {
      box.innerHTML = [...queueCities.values()].map((c, i) => `<span class="chip-toggle queued"><b>${i + 1}</b> ${c.city_name}<small>${c.country}</small><button type="button" class="chip-x" data-remove="${c.city_id}" title="${esc(t('queue.remove'))}">×</button></span>`).join('');
    }
    $('crawl-label').textContent = queueCities.size
      ? t('action.syncCities', { n: queueCities.size })
      : (continueMode ? t('action.syncMore') : t('action.sync'));
  }

  function buildPayload() {
    const amount = Number($('amount').value);
    if (!languages().length) { toast(t('lang.needOne'), 'error'); return null; }
    if (activeTab !== 'ids' && (!Number.isInteger(amount) || amount < 1)) { toast(t('amount.invalid'), 'error'); return null; }
    if (activeTab === 'ids') {
      if (!idsState.ids.length) { toast(t('ids.needCheck'), 'error'); return null; }
      const chosen = idsSelected();
      if (!chosen.length) { toast(t('ids.needPick'), 'error'); return null; }
      return { ids: chosen, ngon_ngu: languages(), cao_lai: $('ids-cao-lai').checked };
    }
    if (queueCities.size) {
      return { city_ids: [...queueCities.keys()], so_luong: amount, ngon_ngu: languages() };
    }
    if (activeTab === 'destination') {
      const city_id = Number($('select-city').value);
      if (!city_id) { toast(t('action.pickCatalogCity'), 'error'); return null; }
      return { city_id, so_luong: amount, ngon_ngu: languages(), tiep_tuc: continueMode };
    }
    const url = $('url').value.trim();
    if (!url) { toast(t('action.pasteUrl'), 'error'); return null; }
    return { url, so_luong: amount, ngon_ngu: languages(), tiep_tuc: continueMode };
  }

  async function sendCrawl(payload) {
    saveForm();
    try {
      if (payload.ids) {
        await post('/api/crawl/start-ids', payload);
        toast(t('action.startedList', { n: payload.ids.length }));
        $('preflight').hidden = true;
        await refreshJob();
        return;
      }
      await post('/api/crawl/start', payload);
      if (payload.city_ids) {
        toast(t('queue.queued', { n: payload.city_ids.length }));
        queueCities.clear();
        renderQueueChips();
      } else {
        toast(continueMode ? t('action.startedMore', { n: payload.so_luong }) : t('action.started'));
      }
      $('preflight').hidden = true;
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  /* ---------- Danh sách ID / URL do người dùng đưa ---------- */
  const idsState = { ids: [], daCo: {}, selected: new Set(), trung: 0, soKhongHieu: 0 };

  function idsSelected() {
    return idsState.ids.filter((id) => idsState.selected.has(id));
  }
  function idsIsComplete(id) {
    const d = idsState.daCo[id];
    return Boolean(d) && languages().every((l) => d[l]);
  }
  function idsUpdateSummary() {
    const chosen = idsSelected();
    const overwrite = $('ids-cao-lai').checked;
    const daDu = chosen.filter(idsIsComplete);
    const willCrawl = overwrite ? chosen.length : chosen.length - daDu.length;
    const chip = (n, label, cls) => `<span class="q-chip ${cls}"><b>${n.toLocaleString('vi-VN')}</b> ${esc(label)}</span>`;
    $('ids-summary').innerHTML = [
      chip(idsState.ids.length, t('ids.chipValid'), idsState.ids.length ? 'ok' : 'bad'),
      chip(chosen.length, t('ids.chipPicked'), 'info'),
      chip(chosen.length - daDu.length, t('ids.chipNew'), 'none'),
      chip(daDu.length, overwrite ? t('ids.chipExistOverwrite') : t('ids.chipExistSkip'), overwrite ? 'warn' : 'none'),
      chip(idsState.trung || 0, t('ids.chipDup'), 'none'),
      chip(idsState.soKhongHieu || 0, t('ids.chipUnknown'), (idsState.soKhongHieu || 0) ? 'warn' : 'none'),
    ].join('');
    // cập nhật nhãn "Sẽ ghi đè" từng dòng + checkbox chọn tất cả
    document.querySelectorAll('#ids-preview tr[data-id]').forEach((tr) => {
      const id = tr.dataset.id;
      const on = idsState.selected.has(id);
      tr.classList.toggle('picked', on);
      const tag = tr.querySelector('.ids-overwrite');
      if (tag) tag.hidden = !(on && overwrite && idsIsComplete(id));
    });
    const all = $('ids-check-all');
    if (all) { all.checked = idsState.ids.length > 0 && chosen.length === idsState.ids.length; all.indeterminate = chosen.length > 0 && chosen.length < idsState.ids.length; }
    $('crawl-label').textContent = willCrawl ? t('action.syncPicked', { n: willCrawl }) : t('action.syncList');
    $('crawl').disabled = willCrawl === 0 && activeTab === 'ids';
    $('amount').value = willCrawl || '';
  }

  function renderIdsResult(r) {
    idsState.ids = r.ids || [];
    idsState.daCo = r.da_co || {};
    idsState.trung = r.trung || 0;
    idsState.soKhongHieu = r.so_khong_hieu || 0;
    idsState.selected = new Set(idsState.ids);   // mặc định tick sẵn tất cả
    $('ids-summary').hidden = false;
    const rows = idsState.ids.slice(0, 500).map((id) => {
      const d = idsState.daCo[id];
      const status = !d ? `<span class="chip none">${esc(t('ids.rowNew'))}</span>`
        : ['vi', 'en'].map((l) => (d[l] === undefined ? '' : `<span class="chip ${d[l] ? 'ok' : 'warn'}">${esc(t(d[l] ? 'ids.rowOk' : 'ids.rowMissing', { lang: l.toUpperCase() }))}</span>`)).join('')
          + `<span class="chip warn ids-overwrite" hidden>${esc(t('ids.rowOverwrite'))}</span>`;
      return `<tr data-id="${id}" class="picked"><td class="col-check"><input type="checkbox" data-pick="${id}" checked></td><td class="mono">${id}</td><td>${d ? esc(d.ten || '') : ''}</td><td>${d ? esc(d.city_name || '') : ''}</td><td>${status}</td></tr>`;
    }).join('');
    const bad = (r.khong_hieu || []).slice(0, 20).map((l) => `<tr><td></td><td class="mono muted">—</td><td colspan="3" class="muted">${esc(t('ids.unknownLine', { line: l }))}</td></tr>`).join('');
    $('ids-preview').hidden = !(rows || bad);
    $('ids-preview').innerHTML = `
      <div class="ids-toolbar">
        <label class="kho-check"><input id="ids-check-all" type="checkbox" checked><span>${esc(t('ids.selectAll'))}<b id="ids-count-all">${idsState.ids.length}</b>)</span></label>
        <button type="button" class="text-button" data-ids-pick="new">${esc(t('ids.pickNew'))}</button>
        <button type="button" class="text-button" data-ids-pick="existing">${esc(t('ids.pickExisting'))}</button>
        <button type="button" class="text-button" data-ids-pick="none">${esc(t('ids.pickNone'))}</button>
      </div>
      <table><thead><tr><th class="col-check"></th><th>${esc(t('ids.thId'))}</th><th>${esc(t('ids.thName'))}</th><th>${esc(t('ids.thCity'))}</th><th>${esc(t('ids.thStatus'))}</th></tr></thead><tbody>${rows}${bad}</tbody></table>${idsState.ids.length > 500 ? `<p class="muted" style="padding:8px 10px">${esc(t('ids.more', { n: idsState.ids.length - 500 }))}</p>` : ''}`;
    idsUpdateSummary();
  }
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function checkIds() {
    const text = $('ids-text').value;
    if (!text.trim()) return toast(t('ids.needInput'), 'error');
    $('ids-check').disabled = true;
    try { renderIdsResult(await post('/api/danh-sach/phan-tich', { text })); }
    catch (error) { toast(error.message, 'error'); }
    finally { $('ids-check').disabled = false; }
  }

  async function uploadIdsFile(file) {
    if (!file) return;
    $('ids-file-name').textContent = t('ids.reading', { name: file.name });
    try {
      const response = await fetch(`/api/danh-sach/tai-file?ten=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || t('error.http', { status: response.status }));
      $('ids-file-name').textContent = t('ids.fileSummary', { name: file.name, lines: data.so_dong, ids: data.ids.length });
      // Đưa ID đọc được vào ô dán để người dùng thấy và sửa được
      const current = $('ids-text').value.trim();
      $('ids-text').value = (current ? current + '\n' : '') + data.ids.join('\n');
      renderIdsResult(await post('/api/danh-sach/phan-tich', { text: $('ids-text').value }));
    } catch (error) { $('ids-file-name').textContent = ''; toast(error.message, 'error'); }
  }

  $('tab-ids').addEventListener('click', () => setTab('ids'));
  $('ids-check').addEventListener('click', checkIds);
  $('ids-browse').addEventListener('click', () => $('ids-file').click());
  $('ids-file').addEventListener('change', () => { uploadIdsFile($('ids-file').files[0]); $('ids-file').value = ''; });
  $('ids-cao-lai').addEventListener('change', () => { if (idsState.ids.length) idsUpdateSummary(); });
  $('ids-preview').addEventListener('change', (e) => {
    if (e.target.id === 'ids-check-all') {
      idsState.selected = e.target.checked ? new Set(idsState.ids) : new Set();
      document.querySelectorAll('#ids-preview input[data-pick]').forEach((cb) => { cb.checked = e.target.checked; });
      idsUpdateSummary();
      return;
    }
    const id = e.target.dataset && e.target.dataset.pick;
    if (!id) return;
    if (e.target.checked) idsState.selected.add(id); else idsState.selected.delete(id);
    idsUpdateSummary();
  });
  $('ids-preview').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-ids-pick]');
    if (!btn) return;
    const mode = btn.dataset.idsPick;
    idsState.selected = new Set(idsState.ids.filter((id) => (mode === 'new' ? !idsState.daCo[id] : mode === 'existing' ? Boolean(idsState.daCo[id]) : false)));
    document.querySelectorAll('#ids-preview input[data-pick]').forEach((cb) => { cb.checked = idsState.selected.has(cb.dataset.pick); });
    idsUpdateSummary();
  });
  $('ids-text').addEventListener('input', () => { idsState.ids = []; idsState.selected = new Set(); $('ids-summary').hidden = true; $('ids-preview').hidden = true; $('crawl-label').textContent = t('action.syncList'); $('crawl').disabled = true; });
  const drop = $('ids-drop');
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => uploadIdsFile(e.dataTransfer.files[0]));

  /* ---------- Kiểm tra trước khi crawl ---------- */
  let pendingPayload = null;

  function renderPreflight(result) {
    const icon = { ok: '✓', warn: '!', fail: '×' };
    $('preflight-list').innerHTML = result.muc.map((m) => `<li class="pf-${m.trang_thai}"><span class="pf-icon">${icon[m.trang_thai]}</span><div><b>${m.ten}</b><span>${m.chi_tiet}</span></div></li>`).join('');
    $('preflight').hidden = false;
    $('preflight').className = `preflight ${result.ket_luan}`;
    const title = $('preflight-title');
    const actions = $('preflight-actions');
    if (result.ket_luan === 'fail') {
      title.textContent = t('preflight.fail');
      actions.hidden = false;
      $('preflight-go').textContent = t('preflight.goFail');
    } else if (result.ket_luan === 'warn') {
      title.textContent = t('preflight.warn');
      actions.hidden = false;
      $('preflight-go').textContent = t('preflight.goWarn');
    } else {
      title.textContent = t('preflight.ok');
      actions.hidden = true;
    }
  }

  async function startCrawl() {
    const payload = buildPayload();
    if (!payload) return;
    pendingPayload = payload;
    $('crawl').disabled = true;
    $('crawl-label').textContent = t('action.checking');
    try {
      const result = await post('/api/kiem-tra', {
        ngon_ngu: payload.ngon_ngu,
        city_id: payload.city_id || (payload.city_ids && payload.city_ids[0]) || null,
      });
      if (result.ket_luan === 'ok') {
        $('preflight').hidden = true;
        await sendCrawl(payload);
      } else {
        renderPreflight(result);
        $('preflight').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } catch (error) {
      // Kiểm tra lỗi (ví dụ server cũ) thì vẫn cho crawl như trước.
      toast(t('preflight.failed', { msg: error.message }), 'error');
      await sendCrawl(payload);
    } finally {
      $('crawl').disabled = false;
      renderQueueChips();
    }
  }

  async function stopCrawl() {
    if (!confirm(t('action.stopConfirm'))) return;
    try {
      await post('/api/crawl/stop');
      toast(t('action.stopping'), 'warning');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function refreshCookie() {
    if (!languages().length) return toast(t('lang.needOne'), 'error');
    try {
      await post('/api/cookie/refresh', { ngon_ngu: languages() });
      toast(t('action.sessionOpening'));
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  function dateTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value.replace('T', ' ') : date.toLocaleString('vi-VN');
  }

  function duration(job) {
    if (!job || !job.started_at) return '';
    const start = new Date(job.started_at).getTime();
    const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
    if (!Number.isFinite(start) || !Number.isFinite(end)) return '';
    const seconds = Math.max(0, Math.round((end - start) / 1000));
    if (seconds < 60) return t('time.seconds', { s: seconds });
    const minutes = Math.floor(seconds / 60);
    return t('time.minutes', { m: minutes, s: seconds % 60 });
  }

  function jobStatus(job) {
    if (job.running) return { text: job.stopping ? t('status.stopping') : t('status.running'), css: 'running' };
    if (job.returncode === 0) return { text: t('status.success'), css: 'success' };
    if (job.returncode === 3) return { text: t('status.partial'), css: 'warning' };
    if (job.stopping) return { text: t('status.stopped'), css: 'warning' };
    return { text: t('status.error'), css: 'failed' };
  }

  function renderQueueStatus(jobs) {
    const box = $('queue-status');
    const queue = jobs.queue || [];
    if (!queue.length) { box.hidden = true; return; }
    box.hidden = false;
    const wait = jobs.queue_wait_seconds || 0;
    const running = Boolean(jobs.current && jobs.current.running);
    const nameOf = (q) => (q.details && q.details.city_name) || q.label;
    const head = running
      ? t('queue.waiting', { n: queue.length })
      : wait ? t('queue.pause', { s: wait, name: nameOf(queue[0]) }) : t('queue.next', { name: nameOf(queue[0]) });
    box.innerHTML = `<div class="queue-status-head"><span>⏳ ${esc(head)}</span><button id="queue-clear" class="text-button danger-text">${esc(t('queue.cancel'))}</button></div>
      <div class="chip-select">${queue.map((q, i) => `<span class="chip-toggle queued"><b>${i + 1}</b> ${esc(nameOf(q))}<small>${(q.details.languages || []).map((l) => l.toUpperCase()).join('+')} · ${q.details.limit}</small><button type="button" class="chip-x" data-dequeue="${q.id}" title="${esc(t('queue.drop'))}">×</button></span>`).join('')}</div>`;
  }

  function renderJob(job) {
    const running = Boolean(job && job.running);
    $('crawl').disabled = running || (activeTab === 'ids' && !idsSelected().length);
    $('cookie').disabled = running;
    $('stop').disabled = !running;
    $('export').disabled = running;

    const status = job ? jobStatus(job) : { text: t('progress.ready'), css: '' };
    $('state').textContent = status.text;
    $('state').className = `badge ${status.css}`;
    $('job-time').textContent = job
      ? `${t('progress.jobTime', { label: jobLabel(job), time: dateTime(job.started_at) })}${duration(job) ? ` · ${duration(job)}` : ''}`
      : t('progress.idle');

    const percent = job && job.total ? Math.min(job.percent || 0, 100) : 0;
    $('bar').style.width = `${percent}%`;
    $('progress-text').textContent = job && job.total
      ? `${job.done.toLocaleString('vi-VN')}/${job.total.toLocaleString('vi-VN')} · ${percent}%`
      : running ? t('progress.working') : '0/0 · 0%';

    const log = $('log');
    const wasBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
    log.textContent = job && job.lines && job.lines.length ? job.lines.join('\n') : t('progress.noLog');
    if (wasBottom) log.scrollTop = log.scrollHeight;
  }

  /* Nhãn ngắn của tác vụ (thay cho job.label do backend đặt, để dịch được). */
  function jobLabel(job) {
    const details = job.details || {};
    if (job.kind === 'crawl') return t('done.whatCity', { city: details.city_name || 'Trip.com' });
    if (job.kind === 'caobu') {
      const n = details.so_khach_san || job.total || 0;
      return details.nguon === 'danh_sach' ? t('done.whatList', { n }) : t('done.whatFill', { n });
    }
    if (job.kind === 'tripadvisor') return t('history.ta', { n: details.so_khach_san || 0 });
    if (job.kind === 'cookie') return t('history.session');
    return job.label;
  }

  function historyTitle(job) {
    const details = job.details || {};
    const langs = (details.languages || []).map((item) => item.toUpperCase()).join(', ');
    if (job.kind === 'crawl') {
      const mode = details.continue_mode ? t('history.syncMore') : t('history.sync');
      return `${mode} ${details.city_name || 'Trip.com'} · ${t('history.hotels', { n: details.limit || job.total || 0 })}${langs ? ` · ${langs}` : ''}`;
    }
    if (job.kind === 'caobu') {
      const what = details.nguon === 'danh_sach' ? t('history.list') : t('history.fill');
      return `${what} ${t('history.hotels', { n: details.so_khach_san || job.total || 0 })}${langs ? ` · ${langs}` : ''}`;
    }
    if (job.kind === 'tripadvisor') {
      return `${t('history.ta', { n: details.so_khach_san || 0 })}${details.lam_lai ? t('history.taRedo') : ''}`;
    }
    return `${t('history.session')}${langs ? ` · ${langs}` : ''}`;
  }

  function renderHistory(history) {
    const box = $('history-list');
    box.innerHTML = '';
    $('clear-history').disabled = !history.length;
    if (!history.length) {
      box.innerHTML = `<p class="empty">${esc(t('history.empty'))}</p>`;
      return;
    }
    history.forEach((job) => {
      const status = jobStatus(job);
      const row = document.createElement('article');
      row.className = 'history-item';
      const dot = document.createElement('span');
      dot.className = `history-dot ${status.css}`;
      const info = document.createElement('div');
      info.className = 'history-info';
      const title = document.createElement('strong');
      title.textContent = historyTitle(job);
      const meta = document.createElement('span');
      meta.textContent = `${dateTime(job.started_at)} · ${duration(job)} · ${status.text}`;
      info.append(title, meta);
      const progress = document.createElement('span');
      progress.className = 'history-progress';
      progress.textContent = job.total ? `${job.done}/${job.total}` : '—';
      const view = document.createElement('button');
      view.className = 'button mini ghost';
      view.textContent = t('history.viewLog');
      view.addEventListener('click', () => showHistory(job));
      row.append(dot, info, progress, view);
      box.appendChild(row);
    });
  }

  async function refreshJob() {
    clearTimeout(timer);
    try {
      const [jobs, progress] = await Promise.all([api('/api/crawl/jobs'), api('/api/tien-do')]);
      renderJob(jobs.current);
      renderQueueStatus(jobs);
      renderHistory(jobs.history || []);
      const vi = progress.theo_ngon_ngu['vi-VN'] || 0;
      const en = progress.theo_ngon_ngu['en-US'] || 0;
      $('raw-count').textContent = t('progress.rawSaved', { n: fmtN(progress.total_raw) });
      $('stat-raw').textContent = progress.total_raw.toLocaleString('vi-VN');
      if (progress.thu_muc_du_lieu) $('data-dir').textContent = progress.thu_muc_du_lieu;
      if (progress.phien_ban) $('app-version').textContent = `v${progress.phien_ban}`;
      $('stat-vi').textContent = vi.toLocaleString('vi-VN');
      $('stat-en').textContent = en.toLocaleString('vi-VN');
      const running = Boolean(jobs.current && jobs.current.running);
      timer = setTimeout(refreshJob, running ? 1200 : 4000);
      if (!running) refreshFiles();
      if (jobWasRunning && !running) {
        refreshCityStats();
        refreshCities();
        document.dispatchEvent(new CustomEvent('job-finished', { detail: jobs.current }));
        showJobDone(jobs.current);
      }
      if (running && !jobWasRunning) {
        $('job-done').hidden = true;
        document.dispatchEvent(new CustomEvent('job-started', { detail: jobs.current }));
      }
      jobWasRunning = running;
    } catch (_) { timer = setTimeout(refreshJob, 4000); }
  }

  const exportCities = new Set();   // city_id đã tick trong phạm vi "theo thành phố"

  function exportScope() {
    const picked = document.querySelector('input[name=export-scope]:checked');
    const fresh = document.querySelector('input[name=export-fresh]:checked');
    const scope = { chi_moi: !fresh || fresh.value === 'new' };
    if (picked && picked.value === 'city') scope.city_ids = [...exportCities];
    return scope;
  }

  let exportCityList = [];
  let newByCity = {};

  function renderExportCities(cities) {
    if (cities) exportCityList = cities;
    const box = $('export-cities');
    if (!exportCityList.length) { box.innerHTML = `<span class="muted">${esc(t('export.noCities'))}</span>`; return; }
    const fresh = document.querySelector('input[name=export-fresh]:checked');
    const onlyNew = !fresh || fresh.value === 'new';
    box.innerHTML = exportCityList.map((c) => {
      const n = newByCity[c.city_id] || 0;
      const label = onlyNew
        ? `<small class="${n ? 'is-new' : ''}">${esc(t('export.newOf', { n: fmtN(n), total: fmtN(c.total_hotels) }))}</small>`
        : `<small>${c.total_hotels.toLocaleString('vi-VN')}</small>`;
      return `<label class="chip-toggle"><input type="checkbox" value="${c.city_id}" ${exportCities.has(c.city_id) ? 'checked' : ''}> ${c.city_name}${label}</label>`;
    }).join('');
  }

  /* ---------- Báo cáo chất lượng trước khi xuất ---------- */
  let qualityIds = [];

  async function refreshQuality() {
    const scope = exportScope();
    const box = $('quality');
    if (scope.city_ids && !scope.city_ids.length) { box.hidden = true; return; }
    try {
      const params = new URLSearchParams();
      if (scope.city_ids) params.set('city_ids', scope.city_ids.join(','));
      if (scope.chi_moi) params.set('chi_moi', '1');
      const q = await api(`/api/kho/chat-luong?${params.toString()}`);
      renderQuality(q, scope);
    } catch (_) { box.hidden = true; }
  }

  function renderQuality(q, scope) {
    const box = $('quality');
    if (!q || !q.tong_pham_vi) { box.hidden = true; $('export-new-count').textContent = t('export.newCount', { n: 0 }); return; }
    box.hidden = false;
    qualityIds = q.cao_bu.ids || [];
    const where = scope && scope.city_ids ? t('quality.cities', { n: scope.city_ids.length }) : t('quality.whole');
    $('quality-sub').textContent = q.chi_moi
      ? t('quality.subNew', { n: fmtN(q.tong), total: fmtN(q.tong_pham_vi), where })
      : t('quality.sub', { n: fmtN(q.tong), where });
    $('export-new-count').textContent = t('export.newCount', { n: fmtN(q.chua_xuat || 0) });
    $('export-new-count').classList.toggle('has-new', (q.chua_xuat || 0) > 0);
    newByCity = q.chua_xuat_theo_thanh_pho || {};
    renderExportCities();
    if (q.chi_moi && !q.tong) {
      $('quality-chips').innerHTML = `<span class="muted">${esc(t('quality.noNew'))}</span>`;
      $('quality-actions').hidden = true;
      box.className = 'quality ok';
      return;
    }
    const chip = (n, label, cls) => `<span class="q-chip ${n ? cls : 'ok'}"><b>${n.toLocaleString('vi-VN')}</b> ${esc(label)}</span>`;
    $('quality-chips').innerHTML = [
      chip(q.du, t('quality.complete'), 'ok'),
      chip(q.dem.mo_ta, t('quality.noDesc'), 'bad'),
      chip(q.dem.chinh_sach, t('quality.noPolicy'), 'bad'),
      chip(q.dem.lan_can, t('quality.noNearby'), 'bad'),
      chip(q.dem.chua_du, t('quality.incomplete'), 'warn'),
      chip(q.dem.thieu_ngon_ngu, t('quality.oneLang'), 'warn'),
      chip(q.thay_doi, t('quality.changed'), 'info'),
    ].join('') + (q.khong_co ? `<span class="q-sep"></span>${[
      chip(q.khong_co.mo_ta, t('quality.tripNoDesc'), 'none'),
      chip(q.khong_co.chinh_sach, t('quality.tripNoPolicy'), 'none'),
      chip(q.khong_co.lan_can, t('quality.tripNoNearby'), 'none'),
    ].join('')}` : '');
    box.className = `quality ${q.thieu ? 'warn' : 'ok'}`;
    const actions = $('quality-actions');
    actions.hidden = !qualityIds.length;
    $('quality-note').textContent = qualityIds.length
      ? t('quality.note', { n: fmtN(qualityIds.length), vi: q.cao_bu.vi, en: q.cao_bu.en })
      : '';
    $('quality-cao-bu').textContent = t('quality.fill', { n: fmtN(qualityIds.length) });
  }

  async function deleteCsv(name) {
    if (!window.confirm(t('export.deleteConfirm', { name }))) return;
    try {
      await post('/api/csv/xoa', { ten: name });
      toast(t('export.deleted', { name }));
      await refreshFiles();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function deleteAllCsv() {
    if (!window.confirm(t('export.deleteAllConfirm'))) return;
    try {
      const r = await post('/api/csv/xoa', { tat_ca: true });
      toast(t('export.deletedN', { n: r.da_xoa }));
      await refreshFiles();
    } catch (error) { toast(error.message, 'error'); }
  }

  function sqlOptions() {
    return {
      bang: ($('sql-table').value || '').trim() || 'splatform_meta.trip_tmp_property_translation',
      on_conflict: $('sql-on-conflict').checked,
      create_table: $('sql-create-table').checked,
      tung_dong: $('sql-per-row').checked,
    };
  }
  function saveSqlOptions() {
    try { localStorage.setItem('crawler-sql', JSON.stringify(sqlOptions())); } catch (_) { /* bỏ qua */ }
    $('sql-table-preview').textContent = sqlOptions().bang;
  }
  function restoreSqlOptions() {
    try {
      const v = JSON.parse(localStorage.getItem('crawler-sql') || 'null');
      if (v) {
        if (v.bang) $('sql-table').value = v.bang;
        if (typeof v.on_conflict === 'boolean') $('sql-on-conflict').checked = v.on_conflict;
        if (typeof v.create_table === 'boolean') $('sql-create-table').checked = v.create_table;
        if (typeof v.tung_dong === 'boolean') $('sql-per-row').checked = v.tung_dong;
      }
    } catch (_) { /* bỏ qua */ }
    $('sql-table-preview').textContent = sqlOptions().bang;
  }

  async function exportFile(fmt, scope) {
    const body = scope && typeof scope === 'object' && !(scope instanceof Event) ? { ...scope } : exportScope();
    body.dinh_dang = fmt;
    if (fmt === 'sql') body.sql = sqlOptions();
    if (body.city_ids && !body.city_ids.length) { toast(t('export.needCity'), 'error'); return null; }
    const btn = fmt === 'sql' ? $('export-sql') : $('export');
    const label = fmt === 'sql' ? t('export.sql') : t('export.csv');
    btn.disabled = true; btn.textContent = t('export.exporting');
    try {
      const result = await post('/api/csv/xuat', body);
      await refreshFiles();
      toast(result.so_khach_san ? t('export.createdN', { name: result.ten, n: fmtN(result.so_khach_san) }) : t('export.created', { name: result.ten }));
      lastCsvName = result.ten;
      refreshQuality();
      $('done-open').hidden = false;
      $('done-export').textContent = t('done.exportAgain');
      return result.ten;
    } catch (error) { toast(error.message, 'error'); return null; }
    finally { btn.disabled = false; btn.textContent = label; }
  }
  const exportCsv = (scope) => exportFile('csv', scope);
  const exportSql = (scope) => exportFile('sql', scope);

  function autoExportFormats() {
    const v = ($('auto-export-format') && $('auto-export-format').value) || 'sql';
    return v === 'both' ? ['sql', 'csv'] : [v];
  }
  async function exportAuto(scope) {
    const names = [];
    for (const fmt of autoExportFormats()) {
      const n = await exportFile(fmt, scope);
      if (n) names.push(n);
    }
    return names.length ? names.join(' + ') : null;
  }

  let lastCsvName = null;

  function notifyDesktop(title, body) {
    try {
      if (!('Notification' in window)) return;
      if (Notification.permission === 'granted') new Notification(title, { body });
      else if (Notification.permission !== 'denied') Notification.requestPermission().then((p) => { if (p === 'granted') new Notification(title, { body }); });
    } catch (_) { /* không hỗ trợ thông báo */ }
  }

  let lastJob = null;

  async function showJobDone(job) {
    lastJob = job;
    const panel = $('job-done');
    if (!job || job.kind === 'cookie') { panel.hidden = true; return; }
    if (job.kind === 'tripadvisor') {
      const okTa = job.returncode === 0;
      panel.hidden = false;
      panel.className = `job-done ${okTa ? 'success' : 'warning'}`;
      $('job-done-icon').textContent = okTa ? '✓' : '!';
      $('job-done-title').textContent = okTa ? t('done.taOk') : t('done.taStopped');
      const last = (job.lines || []).filter((l) => l.includes('TRIPADVISOR · xong') || l.includes('DỪNG')).pop();
      $('job-done-text').textContent = (last ? last.replace(/^TRIPADVISOR · /, '') + '. ' : '') + t('done.taText');
      $('done-open').hidden = true;
      $('done-export').textContent = t('done.exportFmt', { fmt: autoExportFormats().map((f) => f.toUpperCase()).join(' + ') });
      $('done-export').disabled = false;
      refreshTripadvisor();
      return;
    }
    const status = jobStatus(job);
    const details = job.details || {};
    const ok = job.returncode === 0;
    const partial = job.returncode === 3;
    panel.hidden = false;
    panel.className = `job-done ${status.css}`;
    $('job-done-icon').textContent = ok ? '✓' : partial ? '!' : '×';
    const what = jobLabel(job);
    $('job-done-title').textContent = ok ? t('done.ok', { what }) : partial ? t('done.partial', { what }) : t('done.fail', { what });
    const dt = { done: fmtN(job.done), total: fmtN(job.total) };
    $('job-done-text').textContent = ok ? t('done.okText', dt) : partial ? t('done.partialText', dt) : t('done.failText');
    $('done-open').hidden = true;
    $('done-export').textContent = t('done.exportFmt', { fmt: autoExportFormats().map((f) => f.toUpperCase()).join(' + ') });
    $('done-export').disabled = false;
    notifyDesktop(t('app.name'), $('job-done-title').textContent);
    if (job.kind === 'crawl' && details.city_id) {
      try {
        const q = await api(`/api/kho/chat-luong?city_ids=${Number(details.city_id)}`);
        if (q.tong) {
          const parts = [];
          if (q.dem.mo_ta) parts.push(t('done.qMissingDesc', { n: q.dem.mo_ta }));
          if (q.dem.chinh_sach) parts.push(t('done.qMissingPolicy', { n: q.dem.chinh_sach }));
          if (q.dem.lan_can) parts.push(t('done.qMissingNearby', { n: q.dem.lan_can }));
          if (q.thay_doi) parts.push(t('done.qChanged', { n: q.thay_doi }));
          if (q.khong_co && q.khong_co.mo_ta) parts.push(t('done.qNoDesc', { n: q.khong_co.mo_ta }));
          $('job-done-text').textContent += parts.length
            ? t('done.quality', { ok: q.du, total: q.tong, parts: parts.join(', ') })
            : t('done.qualityOk', { ok: q.du, total: q.tong });
        }
      } catch (_) { /* bỏ qua */ }
    }
    if ((ok || partial) && $('auto-export').checked && job.done > 0) {
      $('done-export').disabled = true;
      $('done-export').textContent = t('done.exporting');
      const scope = job.kind === 'crawl' && details.city_id
        ? { city_ids: [Number(details.city_id)], chi_moi: true }
        : { chi_moi: true };
      const name = await exportAuto(scope);
      $('done-export').disabled = false;
      if (name) {
        $('job-done-text').textContent += t('done.autoExported', { name });
        $('done-export').textContent = t('done.exportAgain');
      }
    }
  }

  function bytes(value) {
    if (value < 1024) return `${value} B`;
    if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 ** 2).toFixed(1)} MB`;
  }

  function fileButton(label, className, action) {
    const button = document.createElement('button');
    button.className = `button mini ${className}`;
    button.textContent = label;
    button.addEventListener('click', action);
    return button;
  }

  async function refreshFiles() {
    try {
      const data = await api('/api/csv/danh-sach');
      $('csv-delete-all').hidden = !(data.files && data.files.length);
      const box = $('csv-list');
      box.innerHTML = '';
      $('stat-csv').textContent = data.files.length.toLocaleString('vi-VN');
      if (!data.files.length) {
        box.innerHTML = `<p class="empty">${esc(t('export.noFilesHint'))}</p>`;
        return;
      }
      data.files.forEach((file, index) => {
        const row = document.createElement('article');
        row.className = 'file';
        const icon = document.createElement('span');
        const isSql = file.ten.toLowerCase().endsWith('.sql');
        icon.className = `file-icon${isSql ? ' sql' : ''}`;
        icon.textContent = isSql ? 'SQL' : 'CSV';
        const info = document.createElement('div');
        info.className = 'file-info';
        const name = document.createElement('strong');
        name.textContent = file.ten;
        const meta = document.createElement('span');
        meta.textContent = `${bytes(file.kich_thuoc)} · ${dateTime(file.cap_nhat)}${index === 0 ? t('export.latest') : ''}${file.da_tai ? t('export.downloadedAt', { time: dateTime(file.tai_luc) }) : ''}`;
        info.append(name, meta);
        const actions = document.createElement('div');
        actions.className = 'file-actions';
        actions.append(fileButton(t('export.preview'), 'ghost', () => previewCsv(file.ten)));
        actions.append(fileButton(t('export.open'), 'secondary', () => openCsv(file.ten)));
        if (file.da_tai) {
          const badge = document.createElement('span');
          badge.className = 'downloaded-badge';
          badge.textContent = t('export.downloaded');
          actions.appendChild(badge);
        } else {
          actions.append(fileButton(t('export.download'), 'primary', () => downloadCsv(file.ten)));
        }
        actions.append(fileButton(t('export.delete'), 'danger', () => deleteCsv(file.ten)));
        row.append(icon, info, actions);
        box.appendChild(row);
      });
    } catch (_) { /* Server có thể vừa khởi động. */ }
  }

  function continueCity(item) {
    const params = new URLSearchParams({
      cityId: item.city_id, provinceId: item.province_id || 0,
      countryId: item.country_id || 0, cityName: item.city_name,
    });
    $('url').value = `https://vn.trip.com/hotels/list?${params.toString()}`;
    const inCatalog = selectDestinationByCityId(item.city_id);
    if (inCatalog) {
      setTab('destination');
    } else {
      setTab('custom-url');
    }
    $('lang-vi').checked = true;
    setContinueMode(true);
    saveForm();
    document.querySelector('.setup-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    toast(t('cities.resumeOn', { name: item.city_name }));
  }

  async function refreshCities() {
    try {
      const data = await api('/api/crawl/cities');
      const cities = data.cities || [];
      const box = $('cities-list');
      box.innerHTML = '';
      $('city-count').textContent = t('cities.count', { n: fmtN(cities.length) });
      renderExportCities(cities);
      setTimeout(() => $('cities-search').dispatchEvent(new Event('input')), 0);
      if (!cities.length) {
        box.innerHTML = `<p class="empty">${esc(t('cities.emptyRaw'))}</p>`;
        return;
      }
      cities.forEach((item) => {
        const card = document.createElement('article');
        card.className = 'city-card';
        const head = document.createElement('div');
        head.className = 'city-card-head';
        const avatar = document.createElement('span');
        avatar.className = 'city-avatar';
        avatar.textContent = `#${item.city_id}`;
        const title = document.createElement('div');
        title.className = 'city-card-title';
        const name = document.createElement('strong'); name.textContent = item.city_name;
        const country = document.createElement('span'); country.textContent = item.country_name || `countryId ${item.country_id}`;
        title.append(name, country);
        const total = document.createElement('div');
        total.className = 'city-total';
        total.textContent = item.total_hotels.toLocaleString('vi-VN');
        const totalLabel = document.createElement('small'); totalLabel.textContent = t('cities.hotels');
        total.appendChild(totalLabel);
        head.append(avatar, title, total);

        const metrics = document.createElement('div');
        metrics.className = 'city-metrics';
        const vi = item.languages.vi;
        const en = item.languages.en;
        [
          [t('lang.vi'), t('cities.complete', { a: vi.complete, b: vi.total })],
          [t('lang.en'), t('cities.complete', { a: en.complete, b: en.total })],
          [t('cities.knownIds'), item.listed_hotels.toLocaleString('vi-VN')],
        ].forEach(([label, value]) => {
          const metric = document.createElement('div'); metric.className = 'city-metric';
          const small = document.createElement('span'); small.textContent = label;
          const strong = document.createElement('strong'); strong.textContent = value;
          metric.append(small, strong); metrics.appendChild(metric);
        });

        const foot = document.createElement('div');
        foot.className = 'city-card-foot';
        const updated = document.createElement('span'); updated.textContent = t('cities.updated', { time: dateTime(item.updated_at) });
        const resume = fileButton(t('cities.resume'), 'secondary', () => continueCity(item));
        foot.append(updated, resume);
        card.append(head, metrics, foot);
        card.dataset.search = `${item.city_name} ${item.country_name || ''} ${item.city_id}`
          .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        box.appendChild(card);
      });
    } catch (_) { /* Server có thể đang là phiên cũ, chờ lần khởi động tiếp theo. */ }
  }

  function downloadCsv(name) {
    const link = document.createElement('a');
    link.href = `/api/csv/tai/${encodeURIComponent(name)}`;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    toast(t('export.downloading'));
    setTimeout(refreshFiles, 1400);
  }

  async function openCsv(name) {
    try {
      await post(`/api/csv/mo/${encodeURIComponent(name)}`);
      toast(t('export.opened'));
    } catch (error) { toast(error.message, 'error'); }
  }

  async function openFolder() {
    try {
      await post('/api/csv/mo-thu-muc');
      toast(t('export.folderOpened'));
    } catch (error) { toast(error.message, 'error'); }
  }

  function showModal(title, kicker, content) {
    $('modal-title').textContent = title;
    $('modal-kicker').textContent = kicker;
    const body = $('modal-body');
    body.innerHTML = '';
    body.appendChild(content);
    $('modal').hidden = false;
    document.body.classList.add('modal-open');
  }

  function closeModal() {
    $('modal').hidden = true;
    document.body.classList.remove('modal-open');
  }

  async function previewCsv(name) {
    try {
      const data = await api(`/api/csv/xem/${encodeURIComponent(name)}`);
      const wrapper = document.createElement('div');
      const note = document.createElement('p');
      note.className = 'preview-note';
      note.textContent = t('export.previewNote', { total: fmtN(data.tong_dong), limit: data.gioi_han });
      if (data.sql) {
        const pre = document.createElement('pre');
        pre.className = 'sql-preview';
        pre.textContent = data.lines.join('\n');
        wrapper.append(note, pre);
        showModal(name, t('export.previewSql'), wrapper);
        return;
      }
      const scroll = document.createElement('div');
      scroll.className = 'table-scroll';
      const table = document.createElement('table');
      const head = document.createElement('thead');
      const headRow = document.createElement('tr');
      data.columns.forEach((column) => { const th = document.createElement('th'); th.textContent = column; headRow.appendChild(th); });
      head.appendChild(headRow);
      const tbody = document.createElement('tbody');
      data.rows.forEach((row) => {
        const tr = document.createElement('tr');
        row.forEach((value) => { const td = document.createElement('td'); td.textContent = value; td.title = value; tr.appendChild(td); });
        tbody.appendChild(tr);
      });
      table.append(head, tbody);
      scroll.appendChild(table);
      wrapper.append(note, scroll);
      showModal(name, t('export.previewCsv'), wrapper);
    } catch (error) { toast(error.message, 'error'); }
  }

  function showHistory(job) {
    const wrapper = document.createElement('div');
    const summary = document.createElement('div');
    summary.className = 'history-summary';
    const status = jobStatus(job);
    [
      [t('history.status'), status.text], [t('history.start'), dateTime(job.started_at)],
      [t('history.end'), dateTime(job.finished_at)], [t('history.duration'), duration(job)],
    ].forEach(([label, value]) => {
      const item = document.createElement('div');
      const small = document.createElement('span'); small.textContent = label;
      const strong = document.createElement('strong'); strong.textContent = value || '—';
      item.append(small, strong); summary.appendChild(item);
    });
    const log = document.createElement('pre');
    log.className = 'history-log';
    log.textContent = (job.lines || []).join('\n') || t('history.noLog');
    wrapper.append(summary, log);
    showModal(historyTitle(job), t('history.kicker'), wrapper);
  }

  async function clearHistory() {
    if (!confirm(t('history.clearConfirm'))) return;
    try {
      await post('/api/crawl/history/clear');
      toast(t('history.cleared'));
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function copyLog() {
    try {
      await navigator.clipboard.writeText($('log').textContent);
      toast(t('progress.copied'));
    } catch (_) { toast(t('progress.copyFailed'), 'error'); }
  }

  function setView(name) {
    document.querySelectorAll('.view').forEach((node) => {
      const own = node.id === `view-${name}` || (name === 'crawl' && node.id === 'view-crawl-extra');
      node.classList.toggle('active', own);
    });
    document.querySelectorAll('.view-tab').forEach((node) => {
      node.classList.toggle('active', node.dataset.view === name);
    });
    try { localStorage.setItem('crawler-view', name); } catch (_) { /* bỏ qua */ }
    document.dispatchEvent(new CustomEvent('view-changed', { detail: name }));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  document.querySelectorAll('.view-tab').forEach((node) => node.addEventListener('click', () => setView(node.dataset.view)));
  window.crawlerSetView = setView;
  try { setView(localStorage.getItem('crawler-view') || 'crawl'); } catch (_) { setView('crawl'); }

  $('tab-destination').addEventListener('click', () => setTab('destination'));
  $('tab-custom-url').addEventListener('click', () => setTab('custom-url'));
  // Ô chọn gõ-tìm cho Quốc gia / Thành phố (select gốc vẫn giữ giá trị).
  if (window.makeCombo) {
    window.makeCombo($('select-country'), {
      placeholder: t('setup.countryPlaceholder'),
      items: () => (catalogData.countries || []).map((country) => ({
        value: country,
        label: country,
        tags: (catalogData.country_tags && catalogData.country_tags[country]) || [],
      })),
    });
    window.makeCombo($('select-city'), {
      placeholder: t('setup.cityPlaceholder'),
      // Tìm trên toàn bộ danh mục; chọn thành phố nước khác thì tự đổi quốc gia.
      items: () => Object.entries(catalogData.catalog || {}).flatMap(([country, cities]) =>
        cities.map((c) => ({
          value: c.city_id,
          label: c.city_name,
          extra: country,
          tags: c.tags || [],
          own: country === $('select-country').value,   // thuộc quốc gia đang chọn
          pick: () => {
            if ($('select-country').value !== country) {
              $('select-country').value = country;
              populateCitiesForCountry(country, c.city_id);
            } else {
              $('select-city').value = String(c.city_id);
            }
            $('select-city').dispatchEvent(new Event('change', { bubbles: true }));
          },
        }))),
    });
  }

  $('select-country').addEventListener('change', () => {
    populateCitiesForCountry($('select-country').value);
    scheduleCityStats();
  });
  $('select-city').addEventListener('change', scheduleCityStats);
  $('crawl').addEventListener('click', startCrawl);
  $('stop').addEventListener('click', stopCrawl);
  $('cookie').addEventListener('click', refreshCookie);
  $('export').addEventListener('click', exportCsv);
  /* ---------- Sao lưu & khôi phục ---------- */
  async function refreshBackups() {
    try {
      const data = await api('/api/du-lieu/sao-luu');
      $('backup-dir').textContent = t('backup.dir', { dir: data.thu_muc });
      const box = $('backup-list');
      box.innerHTML = '';
      if (!data.files.length) { box.innerHTML = `<p class="empty">${esc(t('backup.empty'))}</p>`; return; }
      data.files.forEach((file) => {
        const row = document.createElement('div');
        row.className = 'file';
        const icon = document.createElement('div'); icon.className = 'file-icon zip'; icon.textContent = 'ZIP';
        const info = document.createElement('div'); info.className = 'file-info';
        const name = document.createElement('strong'); name.textContent = file.ten;
        const meta = document.createElement('span'); meta.textContent = `${bytes(file.kich_thuoc)} · ${dateTime(file.cap_nhat)}`;
        info.append(name, meta);
        const actions = document.createElement('div'); actions.className = 'file-actions';
        actions.append(fileButton(t('backup.restoreKeep'), 'secondary', () => restoreBackup(file.ten, false)));
        actions.append(fileButton(t('backup.restoreReplace'), 'danger', () => restoreBackup(file.ten, true)));
        actions.append(fileButton(t('backup.delete'), 'ghost', async () => {
          if (!window.confirm(t('backup.deleteConfirm', { name: file.ten }))) return;
          try { await post('/api/du-lieu/xoa-sao-luu', { ten: file.ten }); toast(t('backup.deleted', { name: file.ten })); await refreshBackups(); }
          catch (error) { toast(error.message, 'error'); }
        }));
        row.append(icon, info, actions);
        box.appendChild(row);
      });
    } catch (_) { /* server cũ */ }
  }

  async function createBackup() {
    const btn = $('backup-now');
    btn.disabled = true; btn.textContent = t('backup.zipping');
    try {
      const r = await post('/api/du-lieu/sao-luu');
      toast(t('backup.done', { n: r.so_file, name: r.ten, size: bytes(r.kich_thuoc) }));
      await refreshBackups();
    } catch (error) { toast(error.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = t('backup.now'); }
  }

  async function restoreBackup(name, replace) {
    const msg = replace ? t('backup.restoreReplaceConfirm', { name }) : t('backup.restoreKeepConfirm', { name });
    if (!window.confirm(msg)) return;
    try {
      const r = await post('/api/du-lieu/khoi-phuc', { ten: name, ghi_de: replace });
      toast(t('backup.restored', { n: r.phuc_hoi, skipped: r.bo_qua }));
      refreshJob(); refreshCities(); refreshFiles();
      document.dispatchEvent(new CustomEvent('job-finished', { detail: null }));
    } catch (error) { toast(error.message, 'error'); }
  }

  $('backup-now').addEventListener('click', createBackup);
  $('backup-open').addEventListener('click', async () => { try { await post('/api/du-lieu/mo-thu-muc-sao-luu'); } catch (e) { toast(e.message, 'error'); } });
  document.addEventListener('view-changed', (e) => { if (e.detail === 'csv') refreshBackups(); });
  refreshBackups();

  $('open-folder').addEventListener('click', openFolder);
  $('csv-delete-all').addEventListener('click', deleteAllCsv);
  $('queue-add').addEventListener('click', () => {
    if (activeTab !== 'destination') return toast(t('queue.onlyCatalog'), 'error');
    const info = cityLabel($('select-city').value);
    if (!info) return toast(t('queue.pickCity'), 'error');
    if (queueCities.has(info.city_id)) return toast(t('queue.dup', { name: info.city_name }), 'error');
    queueCities.set(info.city_id, info);
    renderQueueChips();
  });
  $('queue-list').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-remove]');
    if (!btn) return;
    queueCities.delete(Number(btn.dataset.remove));
    renderQueueChips();
  });
  $('queue-status').addEventListener('click', async (e) => {
    try {
      if (e.target.id === 'queue-clear') { await post('/api/crawl/queue/clear'); toast(t('queue.cancelled')); }
      const btn = e.target.closest('[data-dequeue]');
      if (btn) await post('/api/crawl/queue/remove', { id: Number(btn.dataset.dequeue) });
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  });
  $('preflight-close').addEventListener('click', () => { $('preflight').hidden = true; });
  $('preflight-go').addEventListener('click', () => { if (pendingPayload) sendCrawl(pendingPayload); });
  $('preflight-cookie').addEventListener('click', () => { $('preflight').hidden = true; refreshCookie(); });
  $('done-export').addEventListener('click', () => {
    const d = (lastJob && lastJob.details) || {};
    exportAuto(lastJob && lastJob.kind === 'crawl' && d.city_id ? { city_ids: [Number(d.city_id)], chi_moi: true } : { chi_moi: true });
  });
  $('export-sql').addEventListener('click', () => exportSql());
  ['sql-table', 'sql-on-conflict', 'sql-create-table', 'sql-per-row'].forEach((id) => $(id).addEventListener('change', saveSqlOptions));
  $('sql-table').addEventListener('input', saveSqlOptions);
  restoreSqlOptions();
  try { const f = localStorage.getItem('crawler-auto-export-format'); if (f) $('auto-export-format').value = f; } catch (_) { /* bỏ qua */ }
  $('auto-export-format').addEventListener('change', () => { try { localStorage.setItem('crawler-auto-export-format', $('auto-export-format').value); } catch (_) { /* bỏ qua */ } });
  document.querySelectorAll('input[name=export-fresh]').forEach((r) => r.addEventListener('change', refreshQuality));
  $('export-reset-state').addEventListener('click', async () => {
    if (!window.confirm(t('marks.resetConfirm'))) return;
    try { await post('/api/csv/dat-lai-da-xuat'); toast(t('marks.resetDone')); refreshQuality(); }
    catch (error) { toast(error.message, 'error'); }
  });
  $('export-mark-all').addEventListener('click', async () => {
    if (!window.confirm(t('marks.allConfirm'))) return;
    try { const r = await post('/api/csv/danh-dau-da-xuat'); toast(t('marks.allDone', { n: r.so_khach_san })); refreshQuality(); }
    catch (error) { toast(error.message, 'error'); }
  });
  document.querySelectorAll('input[name=export-scope]').forEach((r) => r.addEventListener('change', () => {
    $('export-cities').hidden = exportScope().city_ids === undefined;
    refreshQuality(); refreshTripadvisor();
  }));
  $('export-cities').addEventListener('change', (e) => {
    const id = Number(e.target.value);
    if (e.target.checked) exportCities.add(id); else exportCities.delete(id);
    refreshQuality(); refreshTripadvisor();
  });
  $('quality-cao-bu').addEventListener('click', async () => {
    if (!qualityIds.length) return;
    try {
      await post('/api/kho/cao-bu', { ids: qualityIds, ngon_ngu: ['vi', 'en'] });
      toast(t('quality.fillStarted', { n: qualityIds.length }));
      setView('crawl');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  });
  /* ---------- TripAdvisor (field tripAdvisorId) ---------- */
  async function refreshTripadvisor() {
    const scope = exportScope();
    try {
      const params = new URLSearchParams();
      if (scope.city_ids) params.set('city_ids', scope.city_ids.join(','));
      const s = await api(`/api/tripadvisor/thong-ke?${params.toString()}`);
      $('ta-auto').checked = s.tu_dong !== false;
      $('ta-key-note').textContent = s.co_key
        ? t('ta.keyNote', { key: s.key_che, dir: s.thu_muc })
        : t('ta.noKeyNote');
      const chip = (n, label, cls) => `<span class="q-chip ${cls}"><b>${(n || 0).toLocaleString('vi-VN')}</b> ${esc(label)}</span>`;
      $('ta-stats').innerHTML = s.tong ? [
        chip(s.matched, t('ta.matched'), 'ok'),
        chip(s.review, t('ta.review'), s.review ? 'warn' : 'ok'),
        chip(s.no_match, t('ta.noMatch'), 'none'),
        chip(s.error, t('ta.error'), s.error ? 'bad' : 'ok'),
        chip(s.chua_ghep, t('ta.pending'), s.chua_ghep ? 'info' : 'ok'),
      ].join('') : '';
      $('ta-summary').textContent = !s.co_key
        ? t('ta.noKey')
        : t('ta.summaryStats', { matched: fmtN(s.matched), total: fmtN(s.tong), pending: fmtN(s.chua_ghep) });
      $('ta-run').disabled = !s.co_key;
    } catch (_) { /* server cũ */ }
  }
  $('ta-key-save').addEventListener('click', async () => {
    const key = $('ta-key').value.trim();
    try {
      const r = await post('/api/tripadvisor/cai-dat', { api_key: key });
      $('ta-key').value = '';
      toast(r.co_key ? t('ta.keySaved', { key: r.key_che }) : t('ta.keyRemoved'));
      refreshTripadvisor();
    } catch (error) { toast(error.message, 'error'); }
  });
  $('ta-auto').addEventListener('change', async () => {
    try { await post('/api/tripadvisor/cai-dat', { tu_dong: $('ta-auto').checked }); }
    catch (error) { toast(error.message, 'error'); }
  });
  $('ta-run').addEventListener('click', async () => {
    const scope = exportScope();
    if (scope.city_ids && !scope.city_ids.length) { toast(t('ta.needCity'), 'error'); return; }
    try {
      const r = await post('/api/tripadvisor/ghep', { city_ids: scope.city_ids || [], lam_lai: $('ta-redo').checked });
      toast(t('ta.started', { n: (r.details && r.details.so_khach_san) || '' }));
      setView('crawl');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  });
  document.addEventListener('view-changed', (e) => { if (e.detail === 'csv') { refreshQuality(); refreshTripadvisor(); } });
  document.addEventListener('job-finished', () => setTimeout(() => { refreshQuality(); refreshTripadvisor(); }, 1500));
  $('done-open').addEventListener('click', () => { if (lastCsvName) openCsv(lastCsvName); });
  $('done-kho').addEventListener('click', () => setView('kho'));
  try { const v = localStorage.getItem('crawler-auto-export'); if (v !== null) $('auto-export').checked = v === '1'; } catch (_) { /* bỏ qua */ }
  $('auto-export').addEventListener('change', () => { try { localStorage.setItem('crawler-auto-export', $('auto-export').checked ? '1' : '0'); } catch (_) { /* bỏ qua */ } });
  // Đổi thư mục dữ liệu — chỉ có trong bản Electron (cầu nối preload).
  if (window.tripHotelData && window.tripHotelData.isElectron) {
    $('change-data-dir').hidden = false;
    window.tripHotelData.getDataDir().then((info) => {
      if (info && info.custom) $('reset-data-dir').hidden = false;
    }).catch(() => {});
    $('change-data-dir').addEventListener('click', async () => {
      try {
        const r = await window.tripHotelData.chooseDataDir();
        if (r && r.error) toast(r.error, 'error');
        else if (r && r.restarting) toast(t('footer.restartingNew'));
      } catch (error) { toast(error.message, 'error'); }
    });
    $('reset-data-dir').addEventListener('click', async () => {
      try { const r = await window.tripHotelData.resetDataDir(); if (r && r.restarting) toast(t('footer.restarting')); }
      catch (error) { toast(error.message, 'error'); }
    });
  }
  $('open-log-dir').addEventListener('click', async () => {
    try { await post('/api/du-lieu/mo-thu-muc-log'); } catch (error) { toast(error.message, 'error'); }
  });
  $('open-data-dir').addEventListener('click', async () => {
    try { await post('/api/du-lieu/mo-thu-muc'); } catch (error) { toast(error.message, 'error'); }
  });
  $('clear-history').addEventListener('click', clearHistory);
  $('cities-search').addEventListener('input', () => {
    const q = $('cities-search').value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    let shown = 0;
    document.querySelectorAll('#cities-list .city-card').forEach((card) => {
      const ok = !q || (card.dataset.search || '').includes(q);
      card.hidden = !ok;
      if (ok) shown += 1;
    });
    const empty = $('cities-empty-search');
    if (empty) empty.hidden = shown > 0 || !q;
  });
  $('copy-log').addEventListener('click', copyLog);
  ['url', 'amount', 'lang-vi', 'lang-en'].forEach((id) => $(id).addEventListener('change', saveForm));
  $('url').addEventListener('input', () => { setContinueMode(false); scheduleCityStats(); });
  $('amount').addEventListener('change', scheduleCityStats);
  $('lang-vi').addEventListener('change', scheduleCityStats);
  $('lang-en').addEventListener('change', scheduleCityStats);
  $('cancel-resume').addEventListener('click', () => setContinueMode(false));
  document.querySelectorAll('[data-close-modal]').forEach((node) => node.addEventListener('click', closeModal));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeModal(); });

  restoreForm();
  setContinueMode(false);
  loadDestinations();
  refreshJob();
  refreshFiles();
  refreshCities();
});
