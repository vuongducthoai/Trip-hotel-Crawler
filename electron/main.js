// Khởi động server Python, đợi cổng sẵn sàng rồi mới mở cửa sổ ứng dụng.
const { app, BrowserWindow, dialog } = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const { existsSync } = fs;
const net = require('net');
const http = require('http');
let autoUpdater = null;
try { ({ autoUpdater } = require('electron-updater')); } catch (_) { autoUpdater = null; }
const path = require('path');

let serverProcess = null;

function portDangDuocDung(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port });
    socket.setTimeout(500);
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('error', () => { socket.destroy(); resolve(false); });
    socket.once('timeout', () => { socket.destroy(); resolve(false); });
  });
}

// Thư mục dữ liệu (output/, browser_profile/): ưu tiên thư mục cài đặt để người dùng
// dễ tìm; nếu nơi đó không ghi được (Program Files không có quyền) thì dùng AppData.
function dataDir(root) {
  if (!app.isPackaged) return root;
  const candidate = path.join(path.dirname(process.execPath), 'data');
  try {
    fs.mkdirSync(candidate, { recursive: true });
    const probe = path.join(candidate, '.write-test');
    fs.writeFileSync(probe, 'ok');
    fs.unlinkSync(probe);
    return candidate;
  } catch (_) {
    return app.getPath('userData');
  }
}

function projectRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
}

function pythonCommand(root) {
  if (process.env.TOOL_CRAWLER_PYTHON) return process.env.TOOL_CRAWLER_PYTHON;
  const localPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  if (existsSync(localPython)) return localPython;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function waitForServer(port, timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tryConnect = () => {
      const socket = net.createConnection({ host: '127.0.0.1', port });
      socket.once('connect', () => { socket.destroy(); resolve(); });
      socket.once('error', () => {
        socket.destroy();
        if (Date.now() - started > timeoutMs) reject(new Error('Server Python không khởi động kịp.'));
        else setTimeout(tryConnect, 250);
      });
    };
    tryConnect();
  });
}

async function createWindow() {
  const root = projectRoot();
  if (await portDangDuocDung(8765)) {
    dialog.showErrorBox(
      'App cũ chưa tắt hoàn toàn',
      'Cổng 8765 đang được một tiến trình cũ sử dụng. Hãy đóng các cửa sổ Trip Hotel Data rồi mở lại app.'
    );
    app.quit();
    return;
  }
  const backend = app.isPackaged
    ? path.join(root, 'backend', 'tool-crawler-backend.exe')
    : pythonCommand(root);
  const backendArgs = app.isPackaged ? [] : ['-u', path.join(root, 'server.py')];
  serverProcess = spawn(backend, backendArgs, {
    cwd: root,
    windowsHide: app.isPackaged,
    env: {
      ...process.env,
      // npm start dùng dữ liệu ngay trong project để test và kiểm tra dễ dàng.
      // Bản cài ghi vào <thư mục cài>\data; không ghi được thì rơi về AppData.
      TOOL_CRAWLER_DATA_DIR: dataDir(root),
      TRIP_APP_VERSION: app.getVersion(),
      PYTHONUTF8: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  serverProcess.stdout.on('data', (data) => { process.stdout.write(data); appendAppLog(data); });
  serverProcess.stderr.on('data', (data) => { process.stderr.write(data); appendAppLog(data); });
  serverProcess.on('exit', (code) => appendAppLog(`[electron] backend thoát với mã ${code} lúc ${new Date().toISOString()}\n`));

  try {
    await waitForServer(8765);
  } catch (error) {
    dialog.showErrorBox('Không mở được ứng dụng', app.isPackaged
      ? `${error.message}\n\nHãy cài lại ứng dụng.`
      : `${error.message}\n\nHãy kiểm tra Python và chạy: pip install -r requirements.txt`);
    app.quit();
    return;
  }

  const win = new BrowserWindow({
    width: 1080, height: 820, minWidth: 760, minHeight: 620,
    title: 'Trip Hotel Data',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  await win.loadURL('http://127.0.0.1:8765');
  theoDoiTienDo(win);
  setupAutoUpdate(win);
}

// Hiện tiến độ cào trên thanh taskbar + tiêu đề cửa sổ, để thu nhỏ app vẫn thấy.
function theoDoiTienDo(win) {
  const TITLE = 'Trip Hotel Data';
  let wasRunning = false;
  const tick = () => {
    if (win.isDestroyed()) return;
    const req = http.get('http://127.0.0.1:8765/api/crawl/jobs', { timeout: 1500 }, (res) => {
      let raw = '';
      res.on('data', (chunk) => { raw += chunk; });
      res.on('end', () => {
        if (win.isDestroyed()) return;
        try {
          const job = JSON.parse(raw).current;
          const running = Boolean(job && job.running);
          if (running) {
            const pct = job.total ? Math.min(job.done / job.total, 1) : -1; // -1 = indeterminate
            win.setProgressBar(pct >= 0 ? pct : 2, { mode: pct >= 0 ? 'normal' : 'indeterminate' });
            win.setTitle(job.total
              ? `Đang cào ${job.done}/${job.total} (${Math.round(pct * 100)}%) · ${TITLE}`
              : `${job.label || 'Đang chạy'}… · ${TITLE}`);
          } else {
            if (wasRunning) {
              // Vừa xong: nháy taskbar để gây chú ý rồi xoá thanh tiến độ.
              win.setProgressBar(1);
              if (!win.isFocused()) win.flashFrame(true);
              setTimeout(() => { if (!win.isDestroyed()) win.setProgressBar(-1); }, 2500);
              const ok = job && job.returncode === 0;
              win.setTitle(`${ok ? 'Cào xong' : job && job.returncode === 3 ? 'Cào xong (chưa đủ)' : 'Đã dừng'} · ${TITLE}`);
            } else if (win.getTitle() !== TITLE && !/Cào xong|Đã dừng/.test(win.getTitle())) {
              win.setTitle(TITLE);
            }
          }
          wasRunning = running;
        } catch (_) { /* server chưa sẵn sàng */ }
      });
    });
    req.on('error', () => {});
    req.on('timeout', () => req.destroy());
  };
  const timer = setInterval(tick, 1500);
  win.on('closed', () => clearInterval(timer));
  win.on('focus', () => win.flashFrame(false));
}

function stopServer() {
  if (!serverProcess || serverProcess.killed) return;
  if (process.platform === 'win32') {
    // Chạy đồng bộ để Ctrl+C không kết thúc Electron trước khi server Python được dọn sạch.
    spawnSync('taskkill', ['/pid', String(serverProcess.pid), '/t', '/f'], { windowsHide: true });
  } else {
    serverProcess.kill('SIGTERM');
  }
  serverProcess = null;
}

// ---- Tự cập nhật: đọc URL từ resources/update-url.txt (hoặc biến TRIP_UPDATE_URL) ----
function updateFeedUrl() {
  if (process.env.TRIP_UPDATE_URL) return process.env.TRIP_UPDATE_URL.trim();
  try {
    const text = fs.readFileSync(path.join(projectRoot(), 'update-url.txt'), 'utf8');
    const line = text.split(/\r?\n/).map((l) => l.trim()).find((l) => l && !l.startsWith('#'));
    return line || '';
  } catch (_) { return ''; }
}

function setupAutoUpdate(win) {
  if (!app.isPackaged || !autoUpdater) return;
  const url = updateFeedUrl();
  if (!/^https?:\/\//.test(url)) return;      // chưa cấu hình → không làm gì
  const log = (msg) => { try { fs.appendFileSync(path.join(dataDir(projectRoot()), 'output', 'logs', 'app.log'), `${new Date().toISOString()} [update] ${msg}\n`); } catch (_) { /* */ } };
  try {
    autoUpdater.setFeedURL({ provider: 'generic', url });
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.on('checking-for-update', () => log(`kiểm tra tại ${url}`));
    autoUpdater.on('update-available', (info) => log(`có bản ${info.version}, đang tải…`));
    autoUpdater.on('update-not-available', () => log('đang là bản mới nhất'));
    autoUpdater.on('error', (err) => log(`lỗi: ${err && err.message ? err.message : err}`));
    autoUpdater.on('update-downloaded', async (info) => {
      log(`đã tải xong bản ${info.version}`);
      if (win.isDestroyed()) return;
      const { response } = await dialog.showMessageBox(win, {
        type: 'info', title: 'Trip Hotel Data',
        message: `Đã tải xong bản ${info.version}.`,
        detail: 'Cài ngay sẽ đóng ứng dụng, cài bản mới rồi mở lại. Dữ liệu trong thư mục data được giữ nguyên nếu anh không đổi thư mục cài.\nHoặc chọn "Để sau" — bản mới sẽ tự cài khi anh đóng ứng dụng.',
        buttons: ['Cài ngay và khởi động lại', 'Để sau'], defaultId: 0, cancelId: 1,
      });
      if (response === 0) { stopServer(); autoUpdater.quitAndInstall(false, true); }
    });
    autoUpdater.checkForUpdates().catch((err) => log(`không kiểm tra được: ${err.message}`));
    setInterval(() => autoUpdater.checkForUpdates().catch(() => {}), 6 * 60 * 60 * 1000);
  } catch (err) { log(`không bật được tự cập nhật: ${err.message}`); }
}

// Ghi stdout/stderr của backend ra data/output/logs/app.log khi chạy bản cài (không có console).
function appendAppLog(chunk) {
  if (!app.isPackaged) return;
  try {
    const dir = path.join(dataDir(projectRoot()), 'output', 'logs');
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(path.join(dir, 'app.log'), chunk);
  } catch (_) { /* */ }
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
app.on('before-quit', stopServer);
process.on('SIGINT', () => { stopServer(); app.quit(); });
process.on('SIGTERM', () => { stopServer(); app.quit(); });
process.on('exit', stopServer);
