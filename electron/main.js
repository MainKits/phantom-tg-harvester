const { app, BrowserWindow, dialog } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const fs = require('fs')
const net = require('net')

let mainWindow
let pythonProcess
let splashWindow

// ── Splash screen ────────────────────────────────────────────────────────────
function createSplash() {
  splashWindow = new BrowserWindow({
    width: 400,
    height: 300,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
    backgroundColor: '#00000000',
  })
  // Inline splash HTML
  splashWindow.loadURL(`data:text/html,
    <html>
    <head><style>
      body { margin:0; background:#0a0a0f; display:flex; flex-direction:column;
             align-items:center; justify-content:center; height:100vh;
             font-family:system-ui,sans-serif; color:#fff; border-radius:16px;
             border:1px solid rgba(132,0,255,0.4); overflow:hidden; }
      .logo { font-size:64px; margin-bottom:16px; }
      h1 { font-size:20px; font-weight:800; margin:0 0 8px; }
      p  { font-size:13px; color:#666; margin:0 0 32px; }
      .bar { width:240px; height:4px; background:#1a1a2e; border-radius:4px; overflow:hidden; }
      .fill{ height:100%; width:0%; background:linear-gradient(90deg,#8400ff,#00c8ff);
             border-radius:4px; animation:load 3s ease-in-out forwards; }
      @keyframes load { 0%{width:0%} 80%{width:85%} 100%{width:100%} }
    </style></head>
    <body>
      <div class="logo">👻</div>
      <h1>Phantom TG Harvester</h1>
      <p>Запуск бекенду...</p>
      <div class="bar"><div class="fill"></div></div>
    </body>
    </html>
  `)
}

// ── Main window ───────────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: 'Phantom TG Harvester',
    icon: path.join(__dirname, 'icon.png'),
    backgroundColor: '#0a0a0f',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    frame: true,
    autoHideMenuBar: true,
  })

  const isDev = process.env.NODE_ENV === 'development'
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'))
  }

  mainWindow.once('ready-to-show', () => {
    if (splashWindow) { splashWindow.destroy(); splashWindow = null }
    mainWindow.show()
  })

  mainWindow.on('closed', () => { mainWindow = null })
}

// ── Python backend ────────────────────────────────────────────────────────────
function getPythonExecAndCwd() {
  const isWin = process.platform === 'win32'
  const binName = isWin ? 'backend.exe' : 'backend'

  if (app.isPackaged) {
    const exeDir = path.dirname(process.execPath)
    
    const candidates = [
      path.join(exeDir, binName),
      path.join(process.resourcesPath, binName),
      path.join(process.resourcesPath, '..', 'MacOS', binName),
      path.join(exeDir, '..', 'MacOS', binName),
    ]

    for (const binPath of candidates) {
      if (fs.existsSync(binPath)) {
        if (!isWin) {
          try { fs.chmodSync(binPath, 0o755) } catch {}
        }
        return { exe: binPath, args: [], cwd: path.dirname(binPath) }
      }
    }
  }

  // Development: use system python
  const pyCmd = isWin ? 'python' : (fs.existsSync('/usr/bin/python3') ? '/usr/bin/python3' : 'python3')
  return {
    exe: pyCmd,
    args: ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000'],
    cwd: path.join(__dirname, '..'),
  }
}

function startPythonBackend() {
  const { exe, args, cwd } = getPythonExecAndCwd()
  console.log('[Backend] Starting:', exe, args.join(' '), 'in', cwd)

  pythonProcess = spawn(exe, args, {
    cwd,
    env: { ...process.env },
    windowsHide: process.platform === 'win32',
  })

  pythonProcess.stdout.on('data', d => console.log('[Backend]', d.toString().trim()))
  pythonProcess.stderr.on('data', d => console.log('[Backend ERR]', d.toString().trim()))
  pythonProcess.on('error', (err) => {
    dialog.showErrorBox('Backend Error', `Could not start backend:\n${err.message}`)
  })
}

// ── Wait until backend is ready ───────────────────────────────────────────────
function waitForBackend(port, retries = 40, delay = 500) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const sock = net.createConnection({ port, host: '127.0.0.1' })
      sock.once('connect', () => { sock.destroy(); resolve() })
      sock.once('error', () => {
        if (--retries <= 0) return reject(new Error('Backend did not start'))
        setTimeout(attempt, delay)
      })
    }
    attempt()
  })
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  createSplash()
  startPythonBackend()

  try {
    await waitForBackend(8000)
  } catch (e) {
    dialog.showErrorBox('Помилка запуску', 'Не вдалося запустити бекенд. Перевірте дозволи або перевстановіть програму.')
    app.quit()
    return
  }

  createWindow()
})

app.on('before-quit', () => {
  if (pythonProcess) { try { pythonProcess.kill('SIGTERM') } catch {} }
})

app.on('window-all-closed', () => {
  if (pythonProcess) { try { pythonProcess.kill('SIGTERM') } catch {} }
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
