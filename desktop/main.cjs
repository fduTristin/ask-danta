const { app, BrowserWindow, dialog, Menu, shell, session } = require('electron');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const path = require('node:path');
const readline = require('node:readline');

let backend;
let window;
let quitting = false;
const smoke = process.argv.includes('--smoke');
if (smoke) app.setPath('userData', require('node:fs').mkdtempSync(path.join(require('node:os').tmpdir(), 'ask-danta-smoke-')));
const token = randomBytes(32).toString('hex');

async function start() {
  Menu.setApplicationMenu(null);
  const root = path.join(__dirname, '..');
  const executable = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', process.platform === 'win32' ? 'ask-danta-backend.exe' : 'ask-danta-backend')
    : path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  backend = spawn(executable, app.isPackaged ? [] : [path.join(__dirname, 'backend.py')], {
    windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONPATH: path.join(root, 'backend') },
  });
  backend.stderr.resume(); // Never forward potentially private backend diagnostics.
  backend.stdin.on('error', () => {});
  backend.on('exit', () => {
    if (!quitting) fail(new Error('本地服务已退出，请重新启动应用。'));
  });
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('本地服务启动超时。')), 30000);
    backend.once('error', reject);
    backend.once('exit', () => reject(new Error('本地服务无法启动。')));
    const lines = readline.createInterface({ input: backend.stdout });
    lines.once('line', line => {
      clearTimeout(timer);
      try { resolve(JSON.parse(line).port); } catch { reject(new Error('本地服务启动失败。')); }
    });
    backend.stdin.write(JSON.stringify({ token, data: path.join(app.getPath('userData'), '.private') }) + '\n');
  });
  const origin = `http://127.0.0.1:${port}`;
  let ready = false;
  for (let i = 0; i < 150; i++) {
    try {
      const response = await fetch(`${origin}/api/health`, { headers: { 'x-desktop-token': token }, signal: AbortSignal.timeout(1000) });
      if (response.ok) { ready = true; break; }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  if (!ready) throw new Error('本地服务未就绪。');
  session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
    if (new URL(details.url).origin === origin) details.requestHeaders['x-desktop-token'] = token;
    callback({ requestHeaders: details.requestHeaders });
  });
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  window = new BrowserWindow({ width: 1280, height: 850, minWidth: 760, minHeight: 560, show: !smoke,
    icon: path.join(__dirname, 'icons', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  // macOS normally routes editing accelerators through the application menu.
  window.webContents.on('before-input-event', (event, input) => {
    if (process.platform !== 'darwin' || input.type !== 'keyDown' || !input.meta || input.control || input.alt) return;
    const key = input.key.toLowerCase();
    const action = key === 'z' ? (input.shift ? 'redo' : 'undo')
      : !input.shift ? ({ x: 'cut', c: 'copy', v: 'paste', a: 'selectAll' })[key] : undefined;
    if (action) { event.preventDefault(); window.webContents[action](); }
    else if (key === 'q') { event.preventDefault(); app.quit(); }
    else if (key === 'w') { event.preventDefault(); window.close(); }
  });
  function external(url) {
    try { if (['https:', 'http:'].includes(new URL(url).protocol)) void shell.openExternal(url); } catch {}
  }
  window.webContents.setWindowOpenHandler(({ url }) => { external(url); return { action: 'deny' }; });
  window.webContents.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== origin) { event.preventDefault(); external(url); }
  });
  await window.loadURL(origin);
  if (smoke) {
    if (Menu.getApplicationMenu() !== null || (process.platform !== 'darwin' && window.isMenuBarVisible())) {
      throw new Error('桌面菜单栏未移除。');
    }
    const ok = await window.webContents.executeJavaScript(`fetch('/api/settings').then(r => r.ok && document.querySelector('#root').childElementCount > 0)`);
    if (!ok) throw new Error('桌面页面验证失败。');
    console.log('Desktop smoke passed');
    app.quit();
  }
}

function fail(error) {
  if (quitting) return;
  if (!smoke) dialog.showErrorBox('Ask Danta', error.message);
  else console.error(error.message);
  process.exitCode = 1;
  app.quit();
}
app.on('before-quit', event => {
  if (quitting || !backend || backend.exitCode !== null) return;
  event.preventDefault();
  quitting = true;
  backend.stdin.end();
  const timer = setTimeout(() => { backend.kill(); app.exit(process.exitCode || 0); }, 5000);
  backend.once('exit', () => { clearTimeout(timer); app.exit(process.exitCode || 0); });
});
app.on('window-all-closed', () => app.quit());
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (window) { window.restore(); window.focus(); } });
  app.whenReady().then(start).catch(fail);
}
