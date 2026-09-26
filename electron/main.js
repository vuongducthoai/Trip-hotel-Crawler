// Khởi động server Python, đợi cổng sẵn sàng rồi mới mở cửa sổ ứng dụng.
const { app, BrowserWindow, dialog } = require('electron');
const { spawn, spawnSync } = require('child_process');
const { existsSync } = require('fs');
const net = require('net');
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
      'Cổng 8765 đang được một tiến trình cũ sử dụng. Hãy đóng các cửa sổ Tool Crawler Trip rồi mở lại app.'
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
      // Bản cài mới ghi vào AppData vì thư mục cài đặt không có quyền ghi.
      TOOL_CRAWLER_DATA_DIR: app.isPackaged ? app.getPath('userData') : root,
      PYTHONUTF8: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  serverProcess.stdout.on('data', (data) => process.stdout.write(data));
  serverProcess.stderr.on('data', (data) => process.stderr.write(data));

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
    title: 'Tool Crawler Trip',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  await win.loadURL('http://127.0.0.1:8765');
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

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
app.on('before-quit', stopServer);
process.on('SIGINT', () => { stopServer(); app.quit(); });
process.on('SIGTERM', () => { stopServer(); app.quit(); });
process.on('exit', stopServer);
