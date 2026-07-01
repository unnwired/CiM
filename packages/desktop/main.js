const { app, BrowserWindow, shell, ipcMain } = require('electron');
const fs = require('fs');
const http = require('http');
const path = require('path');
const { spawn } = require('child_process');

const TARGET_URL = process.env.CIM_URL || 'http://127.0.0.1:8000';

function resolveInstallRoot() {
  const candidates = [
    path.resolve(__dirname, '..', '..'),
    path.resolve(__dirname, '..'),
  ];
  for (const root of candidates) {
    const versionFile = path.join(root, 'version.txt');
    const dbFile = path.join(root, 'data', 'nse_data.db');
    if (fs.existsSync(versionFile) || fs.existsSync(dbFile)) {
      return root;
    }
  }
  return path.resolve(__dirname, '..');
}

const ROOT_DIR = resolveInstallRoot();
const LOG_DIR = path.join(ROOT_DIR, 'runtime', 'logs');
const DESKTOP_RENDERER_LOG = path.join(LOG_DIR, 'desktop-renderer.log');
let isQuitting = false;
let isClosePromptOpen = false;
let restartInProgress = false;

app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-http-cache');
app.disableHardwareAcceleration();

try {
  const localAppData = process.env.LOCALAPPDATA || app.getPath('appData');
  const base = path.join(localAppData, 'CiMDesktop');
  fs.mkdirSync(base, { recursive: true });
  app.setPath('userData', path.join(base, 'user-data'));
  app.setPath('sessionData', path.join(base, 'session-data'));
} catch {
  // Use Electron defaults if this setup fails.
}

function logDesktopRenderer(message) {
  const line = `[${new Date().toISOString()}] ${message}\n`;
  try {
    fs.mkdirSync(LOG_DIR, { recursive: true });
    fs.appendFileSync(DESKTOP_RENDERER_LOG, line, 'utf8');
  } catch {
    // Renderer diagnostics must never block app startup.
  }
}

function postStopAll() {
  return new Promise((resolve, reject) => {
    const target = new URL('/api/admin/stop-all', TARGET_URL);
    const req = http.request({
      method: 'POST',
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: target.pathname,
      timeout: 2500,
    }, (res) => {
      res.resume();
      resolve(res.statusCode || 0);
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.end();
  });
}

function devToolsEnabled() {
  return !app.isPackaged || process.env.CIM_DEV_TOOLS === '1';
}

function readInstalledVersion() {
  try {
    const vf = path.join(ROOT_DIR, 'version.txt');
    if (fs.existsSync(vf)) {
      return fs.readFileSync(vf, 'utf8').replace(/^\uFEFF/, '').trim();
    }
  } catch {
    // ignore
  }
  return '';
}

function resolveProductDisplayName() {
  const serverPy = path.join(ROOT_DIR, 'server', 'server.py');
  const packagesServerPy = path.join(ROOT_DIR, 'packages', 'server', 'server.py');
  if (fs.existsSync(serverPy) || fs.existsSync(packagesServerPy)) return 'Charts In Motion Dev';
  const devEnv = String(process.env.CIM_DEV || '').trim().toLowerCase();
  if (devEnv === '1' || devEnv === 'true' || devEnv === 'yes') return 'Charts In Motion Dev';
  return 'Charts In Motion';
}

function resolveWindowTitle() {
  const name = resolveProductDisplayName();
  const ver = readInstalledVersion();
  return ver ? `${name} ${ver}` : name;
}

function resolvePythonExe() {
  const embedded = path.join(ROOT_DIR, 'runtime', 'python', 'python.exe');
  if (fs.existsSync(embedded)) return embedded;
  const venv = path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venv)) return venv;
  return process.env.PYTHON_EXE || 'python';
}

function resolveUvicornApp() {
  const serverPy = path.join(ROOT_DIR, 'server', 'server.py');
  const packagesServerPy = path.join(ROOT_DIR, 'packages', 'server', 'server.py');
  const plaintextDist = fs.existsSync(path.join(ROOT_DIR, 'config', '.cim-plaintext-dist'));
  const encryptedDist = fs.existsSync(path.join(ROOT_DIR, 'server', 'server.pyc.enc')) && !fs.existsSync(serverPy);
  const requireAuth = String(process.env.CIM_REQUIRE_ONLINE_AUTH || '').trim() === '1';
  if (plaintextDist || encryptedDist || requireAuth) {
    return 'server.cim_bootstrap:app';
  }
  if (fs.existsSync(serverPy) || fs.existsSync(packagesServerPy)) {
    return 'server.server:app';
  }
  return 'server.cim_bootstrap:app';
}

function resolveUvicornLauncherArgs(appModule) {
  const launcher = path.join(ROOT_DIR, 'runtime', 'run_uvicorn.py');
  if (fs.existsSync(launcher)) {
    return ['-s', launcher, appModule];
  }
  return ['-s', '-m', 'uvicorn', appModule];
}

function startBackendProcess() {
  const pythonExe = resolvePythonExe();
  const env = { ...process.env };
  const appModule = resolveUvicornApp();
  const child = spawn(
    pythonExe,
    [...resolveUvicornLauncherArgs(appModule), '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: ROOT_DIR,
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
      env,
    },
  );
  child.unref();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForBackendReady(timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      await ping(TARGET_URL);
      return true;
    } catch {
      // keep polling
    }
    await sleep(750);
  }
  return false;
}

async function restartBackendNow() {
  if (restartInProgress) {
    throw new Error('Backend restart already in progress');
  }
  restartInProgress = true;
  try {
    try {
      await postStopAll();
    } catch {
      // backend may already be down
    }
    await sleep(900);
    startBackendProcess();
    const ok = await waitForBackendReady();
    if (!ok) {
      throw new Error('Backend did not come back online in time');
    }
  } finally {
    restartInProgress = false;
  }
}

async function confirmAndShutdown(win) {
  if (isClosePromptOpen) return;
  isClosePromptOpen = true;

  let shouldShutdown = false;
  try {
    shouldShutdown = await win.webContents.executeJavaScript(`
      new Promise((resolve) => {
        const existing = document.getElementById('cim-close-confirm-overlay');
        if (existing) {
          resolve(false);
          return;
        }

        const overlay = document.createElement('div');
        overlay.id = 'cim-close-confirm-overlay';
        overlay.style.position = 'fixed';
        overlay.style.inset = '0';
        overlay.style.background = 'rgba(0,0,0,0.62)';
        overlay.style.zIndex = '2147483646';
        overlay.style.display = 'flex';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';

        const card = document.createElement('div');
        card.style.width = '400px';
        card.style.maxWidth = '94vw';
        card.style.background = 'var(--bg-secondary, #161b22)';
        card.style.border = '1px solid var(--border, #30363d)';
        card.style.borderRadius = '8px';
        card.style.boxShadow = '0 20px 48px rgba(0,0,0,0.6)';
        card.style.color = 'var(--text-primary, #e6edf3)';

        const header = document.createElement('div');
        header.style.padding = '14px 16px';
        header.style.borderBottom = '1px solid var(--border, #30363d)';
        header.style.display = 'flex';
        header.style.alignItems = 'center';
        header.style.justifyContent = 'space-between';

        const title = document.createElement('div');
        title.textContent = 'Shut down Charts In Motion?';
        title.style.fontSize = '15px';
        title.style.fontWeight = '600';
        title.style.color = 'var(--text-primary, #e6edf3)';

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.textContent = '×';
        closeBtn.style.background = 'transparent';
        closeBtn.style.border = 'none';
        closeBtn.style.color = 'var(--text-muted, #8b949e)';
        closeBtn.style.fontSize = '20px';
        closeBtn.style.lineHeight = '1';
        closeBtn.style.cursor = 'pointer';
        closeBtn.style.padding = '0 2px';
        closeBtn.onmouseenter = () => { closeBtn.style.color = '#f85149'; };
        closeBtn.onmouseleave = () => { closeBtn.style.color = 'var(--text-muted, #8b949e)'; };

        const body = document.createElement('div');
        body.style.padding = '14px 16px 8px';
        const desc = document.createElement('p');
        desc.textContent = 'This stops backend services and closes the desktop app.';
        desc.style.margin = '0';
        desc.style.fontSize = '13px';
        desc.style.color = 'var(--text-secondary, #c9d1d9)';
        desc.style.lineHeight = '1.5';
        body.appendChild(desc);

        const footer = document.createElement('div');
        footer.style.padding = '12px 16px 16px';
        footer.style.display = 'flex';
        footer.style.justifyContent = 'flex-end';
        footer.style.gap = '10px';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.style.height = '34px';
        cancelBtn.style.padding = '0 16px';
        cancelBtn.style.borderRadius = '4px';
        cancelBtn.style.border = '1px solid var(--border, #30363d)';
        cancelBtn.style.background = 'var(--bg-tertiary, #0d1117)';
        cancelBtn.style.color = 'var(--text-primary, #e6edf3)';
        cancelBtn.style.cursor = 'pointer';
        cancelBtn.style.fontSize = '13px';

        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.textContent = 'Confirm';
        confirmBtn.style.height = '34px';
        confirmBtn.style.padding = '0 16px';
        confirmBtn.style.borderRadius = '4px';
        confirmBtn.style.border = 'none';
        confirmBtn.style.background = '#f85149';
        confirmBtn.style.color = '#ffffff';
        confirmBtn.style.cursor = 'pointer';
        confirmBtn.style.fontSize = '13px';
        confirmBtn.style.fontWeight = '600';

        const cleanup = (value) => {
          document.removeEventListener('keydown', onKeyDown);
          overlay.remove();
          resolve(value);
        };
        const onKeyDown = (e) => {
          if (e.key === 'Escape') cleanup(false);
          if (e.key === 'Enter') cleanup(true);
        };
        document.addEventListener('keydown', onKeyDown);

        overlay.addEventListener('click', (e) => {
          if (e.target === overlay) cleanup(false);
        });
        closeBtn.addEventListener('click', () => cleanup(false));
        cancelBtn.addEventListener('click', () => cleanup(false));
        confirmBtn.addEventListener('click', () => cleanup(true));

        header.appendChild(title);
        header.appendChild(closeBtn);
        footer.appendChild(cancelBtn);
        footer.appendChild(confirmBtn);
        card.appendChild(header);
        card.appendChild(body);
        card.appendChild(footer);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        confirmBtn.focus();
      });
    `, true);
  } catch {
    shouldShutdown = true;
  }

  if (!shouldShutdown) {
    isClosePromptOpen = false;
    return;
  }

  isQuitting = true;
  isClosePromptOpen = false;
  try {
    await postStopAll();
  } catch {
    // Backend may already be down; still close desktop app.
  }
  app.quit();
  setTimeout(() => app.exit(0), 1200);
}

function ping(url) {
  const healthUrl = url.replace(/\/$/, '') + '/api/health';
  return new Promise((resolve, reject) => {
    const req = http.get(healthUrl, (res) => {
      res.resume();
      if (res.statusCode && res.statusCode >= 200 && res.statusCode < 500) {
        resolve();
      } else {
        reject(new Error(`status ${res.statusCode}`));
      }
    });
    req.on('error', reject);
    req.setTimeout(2500, () => req.destroy(new Error('timeout')));
  });
}

function isAppOrigin(hostname) {
  const host = String(hostname || '').toLowerCase();
  return host === '127.0.0.1' || host === 'localhost';
}

/** Open Screener / TradingView (and similar) in the OS default browser, not a new Electron window. */
function shouldOpenInSystemBrowser(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
    if (isAppOrigin(parsed.hostname)) return false;
    const host = parsed.hostname.toLowerCase();
    if (host === 'screener.in' || host === 'www.screener.in') return true;
    if (host === 'tradingview.com' || host.endsWith('.tradingview.com')) return true;
    return false;
  } catch {
    return false;
  }
}

function openInSystemBrowser(url) {
  if (!shouldOpenInSystemBrowser(url)) return false;
  shell.openExternal(url);
  return true;
}

function setLoadingStatus(win, text, isError = false) {
  if (!win || win.isDestroyed()) return;
  const safe = String(text || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  const color = isError ? '#ff7b72' : '';
  const colorCss = color ? `status.style.color = '${color}';` : '';
  win.webContents.executeJavaScript(`
    (() => {
      const status = document.getElementById('status');
      if (status) {
        status.textContent = '${safe}';
        ${colorCss}
      }
    })();
  `).catch(() => {});
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: resolveWindowTitle(),
    autoHideMenuBar: true,
    show: true,
    backgroundColor: '#0d1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Screener + TradingView: system default browser, not a second Charts In Motion window.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (openInSystemBrowser(url)) return { action: 'deny' };
    return { action: 'allow' };
  });

  win.webContents.on('will-navigate', (event, url) => {
    if (openInSystemBrowser(url)) event.preventDefault();
  });

  win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    logDesktopRenderer(`console level=${level} ${sourceId || ''}:${line || 0} ${message}`);
  });

  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    logDesktopRenderer(`did-fail-load code=${errorCode} url=${validatedURL} description=${errorDescription}`);
  });

  win.webContents.on('render-process-gone', (_event, details) => {
    logDesktopRenderer(`render-process-gone reason=${details.reason} exitCode=${details.exitCode}`);
  });

  win.webContents.session.webRequest.onCompleted({ urls: [`${TARGET_URL}/*`] }, (details) => {
    if (details.statusCode >= 400) {
      logDesktopRenderer(`asset ${details.statusCode} ${details.method} ${details.url}`);
    }
  });

  win.webContents.on('did-finish-load', async () => {
    try {
      const state = await win.webContents.executeJavaScript(`
        JSON.stringify({
          url: location.href,
          title: document.title,
          bodyText: document.body ? document.body.innerText.slice(0, 500) : '',
          rootChildren: document.getElementById('root') ? document.getElementById('root').childElementCount : -1,
          scripts: Array.from(document.scripts).map((s) => s.src || '[inline]'),
          styles: Array.from(document.styleSheets).map((s) => s.href || '[inline]').slice(0, 20)
        })
      `, true);
      logDesktopRenderer(`did-finish-load ${state}`);
    } catch (error) {
      logDesktopRenderer(`did-finish-load diagnostics failed: ${error.message}`);
    }
  });

  win.on('close', (event) => {
    if (isQuitting) return;
    event.preventDefault();
    confirmAndShutdown(win);
  });

  await win.loadFile(path.join(__dirname, 'loading.html'));

  let backendAlreadyUp = false;
  try {
    await ping(TARGET_URL);
    backendAlreadyUp = true;
    setLoadingStatus(win, 'Backend is ready. Loading Charts In Motion…');
  } catch {
    setLoadingStatus(win, 'Starting backend service…');
    startBackendProcess();
  }

  let attempts = 0;
  const maxAttempts = 90; // ~90 seconds (first-run pip repair on new machines)
  const interval = setInterval(async () => {
    if (win.isDestroyed()) {
      clearInterval(interval);
      return;
    }
    attempts += 1;
    if (attempts === 1 || attempts % 5 === 0) {
      setLoadingStatus(win, `Waiting for backend at ${TARGET_URL}… (${attempts}s)`);
    }
    try {
      await ping(TARGET_URL);
      clearInterval(interval);
      setLoadingStatus(win, 'Loading Charts In Motion…');
      await win.loadURL(TARGET_URL);
    } catch {
      if (attempts >= maxAttempts) {
        clearInterval(interval);
        setLoadingStatus(
          win,
          `Backend not reachable at ${TARGET_URL}. Run start_cim.bat from the Charts In Motion folder, or check runtime\\logs\\backend-startup.log.`,
          true,
        );
      }
    }
  }, 1000);
}

app.whenReady().then(async () => {
  ipcMain.handle('cim-open-external', async (_event, url) => {
    const target = String(url || '').trim();
    if (!openInSystemBrowser(target)) {
      throw new Error('URL is not allowed for external open');
    }
    return { ok: true };
  });

  ipcMain.handle('cim-can-restart-backend', async () => devToolsEnabled());
  ipcMain.handle('cim-restart-backend', async (_event, options) => {
    const forAuth = options && options.forAuth === true;
    if (!devToolsEnabled() && !forAuth) {
      throw new Error('Restart backend is disabled outside development mode');
    }
    await restartBackendNow();
    return { ok: true };
  });
  ipcMain.handle('cim-quit', async () => {
    isQuitting = true;
    app.quit();
    return { ok: true };
  });
  ipcMain.handle('cim-quit-for-update', async () => {
    isQuitting = true;
    try {
      await postStopAll();
    } catch {
      // backend may already be stopping for apply
    }
    await sleep(400);
    app.quit();
    return { ok: true };
  });
  ipcMain.handle('cim-can-reload-frontend', async () => devToolsEnabled());
  ipcMain.handle('cim-reload-frontend', async () => {
    if (!devToolsEnabled()) {
      throw new Error('Reload frontend is disabled outside development mode');
    }
    const win = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
    if (!win || win.isDestroyed()) {
      throw new Error('No active Charts In Motion window found');
    }
    await win.loadURL(TARGET_URL);
    return { ok: true };
  });
  await createWindow();
  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  app.quit();
});
