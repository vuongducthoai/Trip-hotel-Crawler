/* Dashboard một trang: cào, theo dõi, xem lịch sử và quản lý CSV. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
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
    if (!response.ok) throw new Error(data.error || `Lỗi ${response.status}`);
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
    $('amount-label').textContent = continueMode
      ? 'Số lượng khách sạn muốn cào thêm'
      : 'Số lượng khách sạn (tổng mục tiêu)';
    if (activeTab === 'ids') return;
    $('crawl-label').textContent = queueCities.size ? `Cào ${queueCities.size} thành phố` : (continueMode ? 'Cào tiếp dữ liệu' : 'Cào dữ liệu');
    $('cancel-resume').hidden = !continueMode;
    $('resume-note').textContent = continueMode
      ? 'Chế độ cào thêm · không tính lại khách sạn đã đủ'
      : 'App tự bỏ qua dữ liệu hoàn chỉnh';
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
    if (isIds) {
      $('amount').dataset.saved = $('amount').dataset.saved || $('amount').value;
      $('amount-label').textContent = 'Số khách sạn trong danh sách (tự tính)';
      $('amount').value = idsState.ids.length || '';
      $('city-status').hidden = true;
      $('crawl-label').textContent = idsState.ids.length ? `Cào ${idsState.ids.length} khách sạn trong danh sách` : 'Cào danh sách';
    } else {
      if ($('amount').dataset.saved) { $('amount').value = $('amount').dataset.saved; delete $('amount').dataset.saved; }
      $('amount-label').textContent = continueMode ? 'Số lượng khách sạn muốn cào thêm' : 'Số lượng khách sạn (tổng mục tiêu)';
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
    $('city-status-title').textContent = 'Đang kiểm tra dữ liệu đã lưu…';
    $('city-status-text').textContent = '';
    try {
      const endpoint = activeTab === 'destination' ? '/api/destinations/preview' : '/api/crawl/thong-ke';
      const data = await post(endpoint, requestBody);
      if (activeTab === 'destination' && data.url && previewUrlNode) {
        previewUrlNode.textContent = `URL tự sinh: ${data.url}`;
      }
      const selected = languages();
      const labels = { vi: 'VI', en: 'EN' };
      const target = Math.max(1, Number($('amount').value) || 1);
      const parts = selected.map((lang) => {
        const item = data.languages[lang] || { total: 0, complete: 0, incomplete: 0 };
        const repair = item.incomplete ? ` · ${item.incomplete} raw cũ sẽ cào lại` : '';
        if (continueMode) {
          return `${labels[lang]}: đã có ${item.complete} · tìm thêm ${target} → mục tiêu ${item.complete + target}${repair}`;
        }
        const remaining = Math.max(0, target - item.complete);
        return `${labels[lang]}: ${item.complete} hoàn chỉnh · còn ${remaining} để đạt ${target}${repair}`;
      });
      const cityName = data.city_name || (data.place && data.place.city_name);
      const countryName = data.country_name || (data.place && data.place.country_name);
      const titleCountry = countryName ? ` (${countryName})` : '';
      $('city-status-title').textContent = `${cityName}${titleCountry} · có thể tiếp tục lượt trước`;
      $('city-status-text').textContent = parts.join('  |  ') || 'Chọn ngôn ngữ để xem thống kê.';
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
      box.innerHTML = '<span class="muted">Chưa có thành phố nào trong hàng đợi — bấm "Cào dữ liệu" sẽ cào thành phố đang chọn.</span>';
    } else {
      box.innerHTML = [...queueCities.values()].map((c, i) => `<span class="chip-toggle queued"><b>${i + 1}</b> ${c.city_name}<small>${c.country}</small><button type="button" class="chip-x" data-remove="${c.city_id}" title="Bỏ khỏi hàng đợi">×</button></span>`).join('');
    }
    $('crawl-label').textContent = queueCities.size
      ? `Cào ${queueCities.size} thành phố`
      : (continueMode ? 'Cào tiếp dữ liệu' : 'Cào dữ liệu');
  }

  function buildPayload() {
    const amount = Number($('amount').value);
    if (!languages().length) { toast('Hãy chọn ít nhất một ngôn ngữ.', 'error'); return null; }
    if (activeTab !== 'ids' && (!Number.isInteger(amount) || amount < 1)) { toast('Số lượng khách sạn không hợp lệ.', 'error'); return null; }
    if (activeTab === 'ids') {
      if (!idsState.ids.length) { toast('Hãy dán ID/URL hoặc nhập file rồi bấm "Kiểm tra danh sách".', 'error'); return null; }
      return { ids: idsState.ids, ngon_ngu: languages(), cao_lai: $('ids-cao-lai').checked };
    }
    if (queueCities.size) {
      return { city_ids: [...queueCities.keys()], so_luong: amount, ngon_ngu: languages() };
    }
    if (activeTab === 'destination') {
      const city_id = Number($('select-city').value);
      if (!city_id) { toast('Hãy chọn thành phố trong danh mục.', 'error'); return null; }
      return { city_id, so_luong: amount, ngon_ngu: languages(), tiep_tuc: continueMode };
    }
    const url = $('url').value.trim();
    if (!url) { toast('Hãy dán URL trang danh sách Trip.com.', 'error'); return null; }
    return { url, so_luong: amount, ngon_ngu: languages(), tiep_tuc: continueMode };
  }

  async function sendCrawl(payload) {
    saveForm();
    try {
      if (payload.ids) {
        await post('/api/crawl/start-ids', payload);
        toast(`Đang cào ${payload.ids.length} khách sạn trong danh sách.`);
        $('preflight').hidden = true;
        await refreshJob();
        return;
      }
      await post('/api/crawl/start', payload);
      if (payload.city_ids) {
        toast(`Đã xếp ${payload.city_ids.length} thành phố vào hàng đợi.`);
        queueCities.clear();
        renderQueueChips();
      } else {
        toast(continueMode ? `Đang tìm và cào thêm ${payload.so_luong} khách sạn.` : 'Đã bắt đầu cào dữ liệu.');
      }
      $('preflight').hidden = true;
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  /* ---------- Danh sách ID / URL do người dùng đưa ---------- */
  const idsState = { ids: [], daCo: {} };

  function renderIdsResult(r) {
    idsState.ids = r.ids || [];
    idsState.daCo = r.da_co || {};
    const daDu = idsState.ids.filter((id) => {
      const d = idsState.daCo[id]; if (!d) return false;
      return languages().every((l) => d[l]);
    });
    const chip = (n, label, cls) => `<span class="q-chip ${cls}"><b>${n.toLocaleString('vi-VN')}</b> ${label}</span>`;
    $('ids-summary').hidden = false;
    $('ids-summary').innerHTML = [
      chip(idsState.ids.length, 'ID hợp lệ', idsState.ids.length ? 'ok' : 'bad'),
      chip(daDu.length, 'đã có đủ trong kho' + ($('ids-cao-lai').checked ? ' (sẽ cào lại)' : ' (sẽ bỏ qua)'), 'info'),
      chip(r.trung || 0, 'trùng lặp đã gộp', 'none'),
      chip(r.so_khong_hieu || 0, 'dòng không hiểu', (r.so_khong_hieu || 0) ? 'warn' : 'none'),
    ].join('');
    const rows = idsState.ids.slice(0, 300).map((id) => {
      const d = idsState.daCo[id];
      const status = !d ? '<span class="muted">chưa có trong kho</span>'
        : ['vi', 'en'].map((l) => (d[l] === undefined ? '' : `<span class="chip ${d[l] ? 'ok' : 'warn'}">${l.toUpperCase()} ${d[l] ? 'đủ' : 'thiếu'}</span>`)).join('');
      return `<tr><td class="mono">${id}</td><td>${d ? esc(d.ten || '') : ''}</td><td>${d ? esc(d.city_name || '') : ''}</td><td>${status}</td></tr>`;
    }).join('');
    const bad = (r.khong_hieu || []).slice(0, 20).map((l) => `<tr><td class="mono muted">—</td><td colspan="3" class="muted">Không hiểu: ${esc(l)}</td></tr>`).join('');
    $('ids-preview').hidden = !(rows || bad);
    $('ids-preview').innerHTML = `<table><thead><tr><th>Hotel ID</th><th>Tên (nếu đã có)</th><th>Thành phố</th><th>Trạng thái</th></tr></thead><tbody>${rows}${bad}</tbody></table>${idsState.ids.length > 300 ? `<p class="muted" style="padding:8px 10px">… và ${idsState.ids.length - 300} ID nữa.</p>` : ''}`;
    $('crawl-label').textContent = idsState.ids.length ? `Cào ${idsState.ids.length} khách sạn trong danh sách` : 'Cào danh sách';
    $('amount').value = idsState.ids.length || '';
  }
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function checkIds() {
    const text = $('ids-text').value;
    if (!text.trim()) return toast('Hãy dán danh sách hoặc nhập file trước.', 'error');
    $('ids-check').disabled = true;
    try { renderIdsResult(await post('/api/danh-sach/phan-tich', { text })); }
    catch (error) { toast(error.message, 'error'); }
    finally { $('ids-check').disabled = false; }
  }

  async function uploadIdsFile(file) {
    if (!file) return;
    $('ids-file-name').textContent = `Đang đọc ${file.name}…`;
    try {
      const response = await fetch(`/api/danh-sach/tai-file?ten=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Lỗi ${response.status}`);
      $('ids-file-name').textContent = `${file.name} · ${data.so_dong} dòng · ${data.ids.length} ID`;
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
  $('ids-cao-lai').addEventListener('change', () => { if (idsState.ids.length) checkIds(); });
  $('ids-text').addEventListener('input', () => { idsState.ids = []; $('ids-summary').hidden = true; $('ids-preview').hidden = true; $('crawl-label').textContent = 'Cào danh sách'; });
  const drop = $('ids-drop');
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => uploadIdsFile(e.dataTransfer.files[0]));

  /* ---------- Kiểm tra trước khi cào ---------- */
  let pendingPayload = null;

  function renderPreflight(result) {
    const icon = { ok: '✓', warn: '!', fail: '×' };
    $('preflight-list').innerHTML = result.muc.map((m) => `<li class="pf-${m.trang_thai}"><span class="pf-icon">${icon[m.trang_thai]}</span><div><b>${m.ten}</b><span>${m.chi_tiet}</span></div></li>`).join('');
    $('preflight').hidden = false;
    $('preflight').className = `preflight ${result.ket_luan}`;
    const title = $('preflight-title');
    const actions = $('preflight-actions');
    if (result.ket_luan === 'fail') {
      title.textContent = 'Không nên cào lúc này';
      actions.hidden = false;
      $('preflight-go').textContent = 'Vẫn cào (không khuyến khích)';
    } else if (result.ket_luan === 'warn') {
      title.textContent = 'Có thể cào, nhưng lưu ý';
      actions.hidden = false;
      $('preflight-go').textContent = 'Cào ngay';
    } else {
      title.textContent = 'Mọi thứ sẵn sàng';
      actions.hidden = true;
    }
  }

  async function startCrawl() {
    const payload = buildPayload();
    if (!payload) return;
    pendingPayload = payload;
    $('crawl').disabled = true;
    $('crawl-label').textContent = 'Đang kiểm tra…';
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
      // Kiểm tra lỗi (ví dụ server cũ) thì vẫn cho cào như trước.
      toast(`Không kiểm tra được (${error.message}); cào luôn.`, 'error');
      await sendCrawl(payload);
    } finally {
      $('crawl').disabled = false;
      renderQueueChips();
    }
  }

  async function stopCrawl() {
    if (!confirm('Dừng tác vụ đang chạy? Dữ liệu đã lưu vẫn được giữ lại.')) return;
    try {
      await post('/api/crawl/stop');
      toast('Đang dừng tác vụ…', 'warning');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function refreshCookie() {
    if (!languages().length) return toast('Hãy chọn ít nhất một ngôn ngữ.', 'error');
    try {
      await post('/api/cookie/refresh', { ngon_ngu: languages() });
      toast('Chrome đang mở để lấy cookie.');
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
    if (seconds < 60) return `${seconds} giây`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes} phút ${seconds % 60} giây`;
  }

  function jobStatus(job) {
    if (job.running) return { text: job.stopping ? 'Đang dừng' : 'Đang chạy', css: 'running' };
    if (job.returncode === 0) return { text: 'Thành công', css: 'success' };
    if (job.returncode === 3) return { text: 'Chưa đủ', css: 'warning' };
    if (job.stopping) return { text: 'Đã dừng', css: 'warning' };
    return { text: 'Có lỗi', css: 'failed' };
  }

  function renderQueueStatus(jobs) {
    const box = $('queue-status');
    const queue = jobs.queue || [];
    if (!queue.length) { box.hidden = true; return; }
    box.hidden = false;
    const wait = jobs.queue_wait_seconds || 0;
    const running = Boolean(jobs.current && jobs.current.running);
    const head = running
      ? `Còn ${queue.length} thành phố chờ sau tác vụ này`
      : wait ? `Nghỉ ${wait} giây rồi cào tiếp ${queue[0].label.replace(/^Cào /, '')}` : `Chuẩn bị cào ${queue[0].label.replace(/^Cào /, '')}`;
    box.innerHTML = `<div class="queue-status-head"><span>⏳ ${head}</span><button id="queue-clear" class="text-button danger-text">Huỷ hàng đợi</button></div>
      <div class="chip-select">${queue.map((q, i) => `<span class="chip-toggle queued"><b>${i + 1}</b> ${q.label.replace(/^Cào /, '')}<small>${(q.details.languages || []).map((l) => l.toUpperCase()).join('+')} · ${q.details.limit}</small><button type="button" class="chip-x" data-dequeue="${q.id}" title="Bỏ">×</button></span>`).join('')}</div>`;
  }

  function renderJob(job) {
    const running = Boolean(job && job.running);
    $('crawl').disabled = running;
    $('cookie').disabled = running;
    $('stop').disabled = !running;
    $('export').disabled = running;

    const status = job ? jobStatus(job) : { text: 'Sẵn sàng', css: '' };
    $('state').textContent = status.text;
    $('state').className = `badge ${status.css}`;
    $('job-time').textContent = job
      ? `${job.label} · bắt đầu ${dateTime(job.started_at)}${duration(job) ? ` · ${duration(job)}` : ''}`
      : 'Chưa có tác vụ đang chạy.';

    const percent = job && job.total ? Math.min(job.percent || 0, 100) : 0;
    $('bar').style.width = `${percent}%`;
    $('progress-text').textContent = job && job.total
      ? `${job.done.toLocaleString('vi-VN')}/${job.total.toLocaleString('vi-VN')} · ${percent}%`
      : running ? 'Đang thực hiện…' : '0/0 · 0%';

    const log = $('log');
    const wasBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
    log.textContent = job && job.lines && job.lines.length ? job.lines.join('\n') : 'Chưa chạy tác vụ nào.';
    if (wasBottom) log.scrollTop = log.scrollHeight;
  }

  function historyTitle(job) {
    const details = job.details || {};
    if (job.kind === 'crawl') {
      const langs = (details.languages || []).map((item) => item.toUpperCase()).join(', ');
      const mode = details.continue_mode ? 'Cào thêm' : 'Cào';
      return `${mode} ${details.city_name || 'Trip.com'} · ${details.limit || job.total || 0} khách sạn${langs ? ` · ${langs}` : ''}`;
    }
    if (job.kind === 'caobu') {
      const langs = (details.languages || []).map((item) => item.toUpperCase()).join(', ');
      const what = details.nguon === 'danh_sach' ? 'Cào danh sách' : 'Cào bù';
      return `${what} ${details.so_khach_san || job.total || 0} khách sạn${langs ? ` · ${langs}` : ''}`;
    }
    return `Lấy lại cookie · ${(details.languages || []).map((item) => item.toUpperCase()).join(', ')}`;
  }

  function renderHistory(history) {
    const box = $('history-list');
    box.innerHTML = '';
    $('clear-history').disabled = !history.length;
    if (!history.length) {
      box.innerHTML = '<p class="empty">Chưa có lịch sử. Các lượt hoàn tất sẽ xuất hiện tại đây.</p>';
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
      view.textContent = 'Xem log';
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
      $('raw-count').textContent = `${progress.total_raw.toLocaleString('vi-VN')} raw đã lưu`;
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
    if (!exportCityList.length) { box.innerHTML = '<span class="muted">Chưa có thành phố nào.</span>'; return; }
    const fresh = document.querySelector('input[name=export-fresh]:checked');
    const onlyNew = !fresh || fresh.value === 'new';
    box.innerHTML = exportCityList.map((c) => {
      const n = newByCity[c.city_id] || 0;
      const label = onlyNew
        ? `<small class="${n ? 'is-new' : ''}">${n.toLocaleString('vi-VN')} mới / ${c.total_hotels.toLocaleString('vi-VN')}</small>`
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
    if (!q || !q.tong_pham_vi) { box.hidden = true; $('export-new-count').textContent = '0 mới'; return; }
    box.hidden = false;
    qualityIds = q.cao_bu.ids || [];
    const where = scope && scope.city_ids ? `${scope.city_ids.length} thành phố` : 'toàn bộ kho';
    $('quality-sub').textContent = q.chi_moi
      ? `${q.tong.toLocaleString('vi-VN')} khách sạn mới chưa xuất (trên ${q.tong_pham_vi.toLocaleString('vi-VN')}) · ${where}`
      : `${q.tong.toLocaleString('vi-VN')} khách sạn · ${where}`;
    $('export-new-count').textContent = `${(q.chua_xuat || 0).toLocaleString('vi-VN')} mới`;
    $('export-new-count').classList.toggle('has-new', (q.chua_xuat || 0) > 0);
    newByCity = q.chua_xuat_theo_thanh_pho || {};
    renderExportCities();
    if (q.chi_moi && !q.tong) {
      $('quality-chips').innerHTML = '<span class="muted">Không có khách sạn mới kể từ lần xuất trước — mọi thứ trong phạm vi này đã nằm trong CSV. Chọn "Gộp tất cả" nếu muốn xuất lại.</span>';
      $('quality-actions').hidden = true;
      box.className = 'quality ok';
      return;
    }
    const chip = (n, label, cls) => `<span class="q-chip ${n ? cls : 'ok'}"><b>${n.toLocaleString('vi-VN')}</b> ${label}</span>`;
    $('quality-chips').innerHTML = [
      chip(q.du, 'đủ 3 phần', 'ok'),
      chip(q.dem.mo_ta, 'thiếu mô tả', 'bad'),
      chip(q.dem.chinh_sach, 'thiếu chính sách', 'bad'),
      chip(q.dem.lan_can, 'thiếu lân cận', 'bad'),
      chip(q.dem.chua_du, 'raw thiếu packet', 'warn'),
      chip(q.dem.thieu_ngon_ngu, 'chỉ 1 ngôn ngữ', 'warn'),
      chip(q.thay_doi, 'có thay đổi so với lần trước', 'info'),
    ].join('') + (q.khong_co ? `<span class="q-sep"></span>${[
      chip(q.khong_co.mo_ta, 'Trip.com không có mô tả', 'none'),
      chip(q.khong_co.chinh_sach, 'Trip.com không có chính sách', 'none'),
      chip(q.khong_co.lan_can, 'Trip.com không có lân cận', 'none'),
    ].join('')}` : '');
    box.className = `quality ${q.thieu ? 'warn' : 'ok'}`;
    const actions = $('quality-actions');
    actions.hidden = !qualityIds.length;
    $('quality-note').textContent = qualityIds.length
      ? `${qualityIds.length.toLocaleString('vi-VN')} khách sạn thiếu dữ liệu (VI ${q.cao_bu.vi}, EN ${q.cao_bu.en}). Cào bù trước khi xuất để CSV đầy đủ hơn — hoặc xuất luôn phần đang có.`
      : '';
    $('quality-cao-bu').textContent = `↻ Cào bù ${qualityIds.length.toLocaleString('vi-VN')} khách sạn thiếu`;
  }

  async function deleteCsv(name) {
    if (!window.confirm(`Xoá file "${name}"? Không hoàn tác được (dữ liệu raw vẫn còn, có thể xuất lại).`)) return;
    try {
      await post('/api/csv/xoa', { ten: name });
      toast(`Đã xoá ${name}`);
      await refreshFiles();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function deleteAllCsv() {
    if (!window.confirm('Xoá TẤT CẢ file CSV trong thư mục output\\csv? Không hoàn tác được (dữ liệu raw vẫn còn, có thể xuất lại).')) return;
    try {
      const r = await post('/api/csv/xoa', { tat_ca: true });
      toast(`Đã xoá ${r.da_xoa} file CSV.`);
      await refreshFiles();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function exportCsv(scope) {
    const body = scope && typeof scope === 'object' && !(scope instanceof Event) ? scope : exportScope();
    if (body.city_ids && !body.city_ids.length) { toast('Hãy tick ít nhất một thành phố để xuất.', 'error'); return null; }
    $('export').disabled = true;
    $('export').textContent = 'Đang xuất…';
    try {
      const result = await post('/api/csv/xuat', body);
      await refreshFiles();
      toast(`Đã tạo ${result.ten}${result.so_khach_san ? ` (${result.so_khach_san.toLocaleString('vi-VN')} khách sạn)` : ''}`);
      lastCsvName = result.ten;
      refreshQuality();
      $('done-open').hidden = false;
      $('done-export').textContent = '⇩ Xuất CSV lại';
      return result.ten;
    } catch (error) { toast(error.message, 'error'); return null; }
    finally { $('export').disabled = false; $('export').textContent = 'Xuất CSV'; }
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
    const status = jobStatus(job);
    const details = job.details || {};
    const ok = job.returncode === 0;
    const partial = job.returncode === 3;
    panel.hidden = false;
    panel.className = `job-done ${status.css}`;
    $('job-done-icon').textContent = ok ? '✓' : partial ? '!' : '×';
    const what = job.kind === 'caobu'
      ? `${details.nguon === 'danh_sach' ? 'Cào danh sách' : 'Cào bù'} ${details.so_khach_san || job.total || 0} khách sạn`
      : `Cào ${details.city_name || 'Trip.com'}`;
    $('job-done-title').textContent = ok ? `${what} · hoàn tất` : partial ? `${what} · chưa đủ số lượng` : `${what} · dừng vì lỗi`;
    $('job-done-text').textContent = ok
      ? `Đã cào ${job.done.toLocaleString('vi-VN')}/${job.total.toLocaleString('vi-VN')} lượt. Dữ liệu nằm trong Kho, sẵn sàng xuất CSV.`
      : partial
        ? `Trip.com chỉ cung cấp ${job.done.toLocaleString('vi-VN')}/${job.total.toLocaleString('vi-VN')} lượt. Phần đã cào vẫn dùng được; bấm "Cào tiếp" sau vài phút để lấy thêm.`
        : 'Xem nhật ký bên dưới để biết nguyên nhân. Dữ liệu đã cào trước khi dừng vẫn được giữ.';
    $('done-open').hidden = true;
    $('done-export').textContent = '⇩ Xuất CSV ngay';
    $('done-export').disabled = false;
    notifyDesktop('Trip Hotel Data', $('job-done-title').textContent);
    if (job.kind === 'crawl' && details.city_id) {
      try {
        const q = await api(`/api/kho/chat-luong?city_ids=${Number(details.city_id)}`);
        if (q.tong) {
          const parts = [];
          if (q.dem.mo_ta) parts.push(`${q.dem.mo_ta} thiếu mô tả`);
          if (q.dem.chinh_sach) parts.push(`${q.dem.chinh_sach} thiếu chính sách`);
          if (q.dem.lan_can) parts.push(`${q.dem.lan_can} thiếu lân cận`);
          if (q.thay_doi) parts.push(`${q.thay_doi} có thay đổi so với lần trước`);
          if (q.khong_co && q.khong_co.mo_ta) parts.push(`${q.khong_co.mo_ta} Trip.com không có mô tả`);
          $('job-done-text').textContent += parts.length
            ? ` Chất lượng: ${q.du}/${q.tong} đủ 3 phần; ${parts.join(', ')} (xem tab File CSV để cào bù).`
            : ` Chất lượng: ${q.du}/${q.tong} khách sạn đủ 3 phần.`;
        }
      } catch (_) { /* bỏ qua */ }
    }
    if ((ok || partial) && $('auto-export').checked && job.done > 0) {
      $('done-export').disabled = true;
      $('done-export').textContent = 'Đang xuất CSV…';
      const scope = job.kind === 'crawl' && details.city_id
        ? { city_ids: [Number(details.city_id)], chi_moi: true }
        : { chi_moi: true };
      const name = await exportCsv(scope);
      $('done-export').disabled = false;
      if (name) {
        $('job-done-text').textContent += ` Đã tự xuất ${name} (chỉ gồm phần vừa cào; vì vậy huy hiệu "mới" ở tab CSV về 0).`;
        $('done-export').textContent = '⇩ Xuất CSV lại';
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
        box.innerHTML = '<p class="empty">Chưa có file CSV. Sau khi cào xong, bấm “Xuất CSV”.</p>';
        return;
      }
      data.files.forEach((file, index) => {
        const row = document.createElement('article');
        row.className = 'file';
        const icon = document.createElement('span');
        icon.className = 'file-icon';
        icon.textContent = 'CSV';
        const info = document.createElement('div');
        info.className = 'file-info';
        const name = document.createElement('strong');
        name.textContent = file.ten;
        const meta = document.createElement('span');
        meta.textContent = `${bytes(file.kich_thuoc)} · ${dateTime(file.cap_nhat)}${index === 0 ? ' · Mới nhất' : ''}${file.da_tai ? ` · Đã tải ${dateTime(file.tai_luc)}` : ''}`;
        info.append(name, meta);
        const actions = document.createElement('div');
        actions.className = 'file-actions';
        actions.append(fileButton('Xem trước', 'ghost', () => previewCsv(file.ten)));
        actions.append(fileButton('Mở', 'secondary', () => openCsv(file.ten)));
        if (file.da_tai) {
          const badge = document.createElement('span');
          badge.className = 'downloaded-badge';
          badge.textContent = '✓ Đã tải';
          actions.appendChild(badge);
        } else {
          actions.append(fileButton('Tải về', 'primary', () => downloadCsv(file.ten)));
        actions.append(fileButton('Xoá', 'danger', () => deleteCsv(file.ten)));
        }
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
    toast(`Đã bật cào tiếp ${item.city_name}. Nhập số lượng muốn cào thêm.`);
  }

  async function refreshCities() {
    try {
      const data = await api('/api/crawl/cities');
      const cities = data.cities || [];
      const box = $('cities-list');
      box.innerHTML = '';
      $('city-count').textContent = `${cities.length.toLocaleString('vi-VN')} thành phố`;
      renderExportCities(cities);
      setTimeout(() => $('cities-search').dispatchEvent(new Event('input')), 0);
      if (!cities.length) {
        box.innerHTML = '<p class="empty">Chưa có thành phố nào trong dữ liệu raw.</p>';
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
        const totalLabel = document.createElement('small'); totalLabel.textContent = 'khách sạn raw';
        total.appendChild(totalLabel);
        head.append(avatar, title, total);

        const metrics = document.createElement('div');
        metrics.className = 'city-metrics';
        const vi = item.languages.vi;
        const en = item.languages.en;
        [
          ['Tiếng Việt', `${vi.complete}/${vi.total} đủ`],
          ['English', `${en.complete}/${en.total} đủ`],
          ['ID đã biết', item.listed_hotels.toLocaleString('vi-VN')],
        ].forEach(([label, value]) => {
          const metric = document.createElement('div'); metric.className = 'city-metric';
          const small = document.createElement('span'); small.textContent = label;
          const strong = document.createElement('strong'); strong.textContent = value;
          metric.append(small, strong); metrics.appendChild(metric);
        });

        const foot = document.createElement('div');
        foot.className = 'city-card-foot';
        const updated = document.createElement('span'); updated.textContent = `Cập nhật ${dateTime(item.updated_at)}`;
        const resume = fileButton('Cào tiếp', 'secondary', () => continueCity(item));
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
    toast('Đang tải file CSV…');
    setTimeout(refreshFiles, 1400);
  }

  async function openCsv(name) {
    try {
      await post(`/api/csv/mo/${encodeURIComponent(name)}`);
      toast('Đã mở file bằng ứng dụng mặc định.');
    } catch (error) { toast(error.message, 'error'); }
  }

  async function openFolder() {
    try {
      await post('/api/csv/mo-thu-muc');
      toast('Đã mở thư mục chứa CSV.');
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
      note.textContent = `Tổng ${data.tong_dong.toLocaleString('vi-VN')} dòng · đang hiển thị tối đa ${data.gioi_han} dòng đầu.`;
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
      showModal(name, 'XEM TRƯỚC CSV', wrapper);
    } catch (error) { toast(error.message, 'error'); }
  }

  function showHistory(job) {
    const wrapper = document.createElement('div');
    const summary = document.createElement('div');
    summary.className = 'history-summary';
    const status = jobStatus(job);
    [
      ['Trạng thái', status.text], ['Bắt đầu', dateTime(job.started_at)],
      ['Kết thúc', dateTime(job.finished_at)], ['Thời lượng', duration(job)],
    ].forEach(([label, value]) => {
      const item = document.createElement('div');
      const small = document.createElement('span'); small.textContent = label;
      const strong = document.createElement('strong'); strong.textContent = value || '—';
      item.append(small, strong); summary.appendChild(item);
    });
    const log = document.createElement('pre');
    log.className = 'history-log';
    log.textContent = (job.lines || []).join('\n') || 'Không có log.';
    wrapper.append(summary, log);
    showModal(historyTitle(job), 'LỊCH SỬ TÁC VỤ', wrapper);
  }

  async function clearHistory() {
    if (!confirm('Xóa toàn bộ lịch sử tác vụ? Dữ liệu raw và CSV sẽ không bị xóa.')) return;
    try {
      await post('/api/crawl/history/clear');
      toast('Đã xóa lịch sử.');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  }

  async function copyLog() {
    try {
      await navigator.clipboard.writeText($('log').textContent);
      toast('Đã sao chép log.');
    } catch (_) { toast('Không thể sao chép log.', 'error'); }
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
      placeholder: 'Gõ tên quốc gia hoặc #Vinfast, #GreenSM…',
      items: () => (catalogData.countries || []).map((country) => ({
        value: country,
        label: country,
        tags: (catalogData.country_tags && catalogData.country_tags[country]) || [],
      })),
    });
    window.makeCombo($('select-city'), {
      placeholder: 'Gõ tên thành phố (vd. hk, bang) hoặc #Vinfast, #GreenSM…',
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
      $('backup-dir').textContent = `Lưu tại ${data.thu_muc}`;
      const box = $('backup-list');
      box.innerHTML = '';
      if (!data.files.length) { box.innerHTML = '<p class="empty">Chưa có bản sao lưu.</p>'; return; }
      data.files.forEach((file) => {
        const row = document.createElement('div');
        row.className = 'file';
        const icon = document.createElement('div'); icon.className = 'file-icon zip'; icon.textContent = 'ZIP';
        const info = document.createElement('div'); info.className = 'file-info';
        const name = document.createElement('strong'); name.textContent = file.ten;
        const meta = document.createElement('span'); meta.textContent = `${bytes(file.kich_thuoc)} · ${dateTime(file.cap_nhat)}`;
        info.append(name, meta);
        const actions = document.createElement('div'); actions.className = 'file-actions';
        actions.append(fileButton('Khôi phục (giữ file mới hơn)', 'secondary', () => restoreBackup(file.ten, false)));
        actions.append(fileButton('Khôi phục ghi đè', 'danger', () => restoreBackup(file.ten, true)));
        actions.append(fileButton('Xoá', 'ghost', async () => {
          if (!window.confirm(`Xoá bản sao lưu "${file.ten}"?`)) return;
          try { await post('/api/du-lieu/xoa-sao-luu', { ten: file.ten }); toast(`Đã xoá ${file.ten}`); await refreshBackups(); }
          catch (error) { toast(error.message, 'error'); }
        }));
        row.append(icon, info, actions);
        box.appendChild(row);
      });
    } catch (_) { /* server cũ */ }
  }

  async function createBackup() {
    const btn = $('backup-now');
    btn.disabled = true; btn.textContent = 'Đang nén…';
    try {
      const r = await post('/api/du-lieu/sao-luu');
      toast(`Đã sao lưu ${r.so_file} file → ${r.ten} (${bytes(r.kich_thuoc)})`);
      await refreshBackups();
    } catch (error) { toast(error.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = '⛁ Sao lưu ngay'; }
  }

  async function restoreBackup(name, replace) {
    const msg = replace
      ? `Khôi phục "${name}" và GHI ĐÈ dữ liệu hiện có trùng tên? Không hoàn tác được.`
      : `Khôi phục "${name}"? File đã có trên máy sẽ được giữ nguyên, chỉ thêm file còn thiếu.`;
    if (!window.confirm(msg)) return;
    try {
      const r = await post('/api/du-lieu/khoi-phuc', { ten: name, ghi_de: replace });
      toast(`Đã khôi phục ${r.phuc_hoi} file, bỏ qua ${r.bo_qua} file đã có.`);
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
    if (activeTab !== 'destination') return toast('Hàng đợi chỉ dùng với thành phố trong danh mục.', 'error');
    const info = cityLabel($('select-city').value);
    if (!info) return toast('Hãy chọn thành phố trước.', 'error');
    if (queueCities.has(info.city_id)) return toast(`${info.city_name} đã có trong hàng đợi.`, 'error');
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
      if (e.target.id === 'queue-clear') { await post('/api/crawl/queue/clear'); toast('Đã huỷ hàng đợi.'); }
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
    exportCsv(lastJob && lastJob.kind === 'crawl' && d.city_id ? { city_ids: [Number(d.city_id)], chi_moi: true } : { chi_moi: true });
  });
  document.querySelectorAll('input[name=export-fresh]').forEach((r) => r.addEventListener('change', refreshQuality));
  $('export-reset-state').addEventListener('click', async () => {
    if (!window.confirm('Quên dấu "đã xuất"?\n\nSau đó TOÀN BỘ khách sạn trong kho sẽ được coi là "mới" và lần xuất "chỉ dữ liệu mới" kế tiếp sẽ gồm tất cả. Chỉ dùng khi muốn xuất lại từ đầu.')) return;
    try { await post('/api/csv/dat-lai-da-xuat'); toast('Đã quên dấu đã xuất — mọi khách sạn giờ là "mới".'); refreshQuality(); }
    catch (error) { toast(error.message, 'error'); }
  });
  $('export-mark-all').addEventListener('click', async () => {
    if (!window.confirm('Đánh dấu TẤT CẢ khách sạn trong kho là đã xuất (không tạo file)?\n\nSau đó chỉ những khách sạn cào thêm / cào lại mới được tính là "mới".')) return;
    try { const r = await post('/api/csv/danh-dau-da-xuat'); toast(`Đã đánh dấu ${r.so_khach_san} khách sạn là đã xuất.`); refreshQuality(); }
    catch (error) { toast(error.message, 'error'); }
  });
  document.querySelectorAll('input[name=export-scope]').forEach((r) => r.addEventListener('change', () => {
    $('export-cities').hidden = exportScope().city_ids === undefined;
    refreshQuality();
  }));
  $('export-cities').addEventListener('change', (e) => {
    const id = Number(e.target.value);
    if (e.target.checked) exportCities.add(id); else exportCities.delete(id);
    refreshQuality();
  });
  $('quality-cao-bu').addEventListener('click', async () => {
    if (!qualityIds.length) return;
    try {
      await post('/api/kho/cao-bu', { ids: qualityIds, ngon_ngu: ['vi', 'en'] });
      toast(`Đang cào bù ${qualityIds.length} khách sạn. Xong sẽ tự xuất CSV nếu bật tự động.`);
      setView('crawl');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
  });
  document.addEventListener('view-changed', (e) => { if (e.detail === 'csv') refreshQuality(); });
  document.addEventListener('job-finished', () => setTimeout(refreshQuality, 1500));
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
        else if (r && r.restarting) toast('Đang khởi động lại với thư mục mới…');
      } catch (error) { toast(error.message, 'error'); }
    });
    $('reset-data-dir').addEventListener('click', async () => {
      try { const r = await window.tripHotelData.resetDataDir(); if (r && r.restarting) toast('Đang khởi động lại…'); }
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
})();
