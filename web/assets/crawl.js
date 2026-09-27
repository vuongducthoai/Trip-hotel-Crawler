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
      url: $('url').value, amount: $('amount').value,
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
    $('crawl-label').textContent = continueMode ? 'Cào tiếp dữ liệu' : 'Cào dữ liệu';
    $('cancel-resume').hidden = !continueMode;
    $('resume-note').textContent = continueMode
      ? 'Chế độ cào thêm · không tính lại khách sạn đã đủ'
      : 'App tự bỏ qua dữ liệu hoàn chỉnh';
    scheduleCityStats();
  }

  function setTab(tabName) {
    activeTab = tabName;
    const isDest = tabName === 'destination';
    $('tab-destination').classList.toggle('active', isDest);
    $('tab-destination').setAttribute('aria-selected', isDest ? 'true' : 'false');
    $('tab-custom-url').classList.toggle('active', !isDest);
    $('tab-custom-url').setAttribute('aria-selected', !isDest ? 'true' : 'false');
    $('pane-destination').hidden = !isDest;
    $('pane-custom-url').hidden = isDest;
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
      opt.textContent = city.city_name;
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
        opt.textContent = country;
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

  async function startCrawl() {
    const amount = Number($('amount').value);
    if (!languages().length) return toast('Hãy chọn ít nhất một ngôn ngữ.', 'error');
    if (!Number.isInteger(amount) || amount < 1) return toast('Số lượng khách sạn không hợp lệ.', 'error');
    let payload = {};
    if (activeTab === 'destination') {
      const city_id = Number($('select-city').value);
      if (!city_id) return toast('Hãy chọn thành phố trong danh mục.', 'error');
      payload = { city_id, so_luong: amount, ngon_ngu: languages(), tiep_tuc: continueMode };
    } else {
      const url = $('url').value.trim();
      if (!url) return toast('Hãy dán URL trang danh sách Trip.com.', 'error');
      payload = { url, so_luong: amount, ngon_ngu: languages(), tiep_tuc: continueMode };
    }
    saveForm();
    try {
      await post('/api/crawl/start', payload);
      toast(continueMode ? `Đang tìm và cào thêm ${amount} khách sạn.` : 'Đã bắt đầu cào dữ liệu.');
      await refreshJob();
    } catch (error) { toast(error.message, 'error'); }
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
      renderHistory(jobs.history || []);
      const vi = progress.theo_ngon_ngu['vi-VN'] || 0;
      const en = progress.theo_ngon_ngu['en-US'] || 0;
      $('raw-count').textContent = `${progress.total_raw.toLocaleString('vi-VN')} raw đã lưu`;
      $('stat-raw').textContent = progress.total_raw.toLocaleString('vi-VN');
      $('stat-vi').textContent = vi.toLocaleString('vi-VN');
      $('stat-en').textContent = en.toLocaleString('vi-VN');
      const running = Boolean(jobs.current && jobs.current.running);
      timer = setTimeout(refreshJob, running ? 1200 : 4000);
      if (!running) refreshFiles();
      if (jobWasRunning && !running) {
        refreshCityStats();
        refreshCities();
      }
      jobWasRunning = running;
    } catch (_) { timer = setTimeout(refreshJob, 4000); }
  }

  async function exportCsv() {
    $('export').disabled = true;
    $('export').textContent = 'Đang xuất…';
    try {
      const result = await post('/api/csv/xuat');
      await refreshFiles();
      toast(`Đã tạo ${result.ten}`);
    } catch (error) { toast(error.message, 'error'); }
    finally { $('export').disabled = false; $('export').textContent = 'Xuất CSV'; }
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

  $('tab-destination').addEventListener('click', () => setTab('destination'));
  $('tab-custom-url').addEventListener('click', () => setTab('custom-url'));
  $('select-country').addEventListener('change', () => {
    populateCitiesForCountry($('select-country').value);
    scheduleCityStats();
  });
  $('select-city').addEventListener('change', scheduleCityStats);
  $('crawl').addEventListener('click', startCrawl);
  $('stop').addEventListener('click', stopCrawl);
  $('cookie').addEventListener('click', refreshCookie);
  $('export').addEventListener('click', exportCsv);
  $('open-folder').addEventListener('click', openFolder);
  $('clear-history').addEventListener('click', clearHistory);
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
