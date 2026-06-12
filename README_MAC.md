# Charts In Motion — Mac Setup & Run Guide

> **Platform note:** CiM was originally built for Windows. All `.bat` / `.ps1` scripts are Windows-only.  
> This guide covers everything you need to run CiM natively on **macOS (Intel or Apple Silicon)**.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Project Structure Overview](#2-project-structure-overview)
3. [First-Time Setup](#3-first-time-setup)
4. [Running the App](#4-running-the-app)
   - [Option A — One-click script (recommended)](#option-a--one-click-script-recommended)
   - [Option B — Browser dev mode (manual)](#option-b--browser-dev-mode-manual)
   - [Option C — Electron desktop window](#option-c--electron-desktop-window)
5. [Stopping the App](#5-stopping-the-app)
6. [Seeding Data](#6-seeding-data)
7. [Environment Variables](#7-environment-variables)
8. [Troubleshooting](#8-troubleshooting)
9. [Running Tests](#9-running-tests)
10. [Building a Production Frontend](#10-building-a-production-frontend)

---

## 1. Prerequisites

Install these tools before anything else.

| Tool | Minimum Version | How to install |
|------|----------------|----------------|
| **Python** | 3.11+ | `brew install python@3.11` or [python.org](https://python.org) |
| **Node.js + npm** | 18+ | `brew install node` or [nodejs.org](https://nodejs.org) |
| **Homebrew** *(optional but handy)* | any | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |

### Verify your installs

```bash
python3 --version   # should say 3.11.x or higher
node --version      # should say v18.x or higher
npm --version       # should say 9.x or higher
```

---

## 2. Project Structure Overview

```text
CiM/
├── server/             FastAPI backend (Python)
│   └── server.py       Main API server entry point
├── frontend/           React UI
│   ├── src/            React source code
│   └── build/          Production build (if generated)
├── desktop/            Electron desktop shell
│   └── main.js         Electron entry point
├── data/               SQLite database + user data (gitignored)
├── config/             Product & update config JSON files
├── runtime/logs/       Log files created at runtime
├── .venv/              Python virtualenv (created on first run)
├── requirements_runtime.txt   Python dependencies
├── create_dev_db.py    Creates the SQLite database + seeds sample stocks
├── seed_ohlcv.py       Seeds 2 years of OHLCV candle data for sample stocks
│
│ ── Mac-specific scripts ──────────────────────────────────────────
├── start_cim_mac.sh    One-click Mac launcher
└── stop_cim_mac.sh     Mac stop script
```

> **What runs where:**
> - **Backend** = Python/FastAPI/uvicorn → `http://127.0.0.1:8000`
> - **Frontend (dev mode)** = React dev server → `http://localhost:3000`  
> - **Frontend (prod mode)** = served by the backend from `frontend/build/`

---

## 3. First-Time Setup

> **Do this once.** After setup, just use `start_cim_mac.sh` every time.

### Step 1 — Open Terminal and go to the project folder

```bash
cd /Users/jayprakash/Desktop/CiM
```

### Step 2 — Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install Python backend dependencies

```bash
pip install -r requirements_runtime.txt
```

The packages installed are:

| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP API framework |
| `uvicorn` | ASGI server to run FastAPI |
| `pandas` | Data processing |
| `yfinance` | Market data fetching |
| `tradingview-screener` | Stock screener data |
| `requests` | HTTP client |
| `cryptography` | License / encryption utilities |
| `cachetools` | Thread-safe TTL caching |

### Step 4 — Create the database

```bash
python create_dev_db.py
```

This creates `data/nse_data.db` with all required tables and seeds **10 sample NSE stocks** (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, BHARTIARTL, WIPRO, SBIN, LT, TATAMOTORS).

### Step 5 — Seed OHLCV candle data *(optional but recommended)*

```bash
python seed_ohlcv.py
```

This generates **2 years of realistic daily OHLCV** candle data for the 10 sample stocks so charts are not empty.

### Step 6 — Install frontend npm packages

```bash
cd frontend
npm install
cd ..
```

---

## 4. Running the App

### Option A — One-click script (recommended)

This is the Mac equivalent of `start_cim.bat`. It handles everything automatically:

```bash
bash start_cim_mac.sh
```

**What it does:**
1. Detects or creates the `.venv` virtualenv
2. Installs/verifies Python dependencies
3. Creates the database if missing
4. Starts the FastAPI backend (uvicorn) on port 8000
5. Waits until backend is healthy
6. If `frontend/build` exists: opens `http://127.0.0.1:8000` in your browser
7. If no build: starts the React dev server and opens `http://localhost:3000`

Press **Ctrl+C** to stop everything, or run `bash stop_cim_mac.sh` in another terminal.

---

### Option B — Browser dev mode (manual)

Run each part in a **separate terminal window**.

#### Terminal 1 — Start the backend

```bash
cd /Users/jayprakash/Desktop/CiM
source .venv/bin/activate
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000 --reload
```

> The `--reload` flag auto-restarts the server when you edit Python files (dev convenience).

#### Terminal 2 — Start the React frontend

```bash
cd /Users/jayprakash/Desktop/CiM/frontend
npm start
```

#### Open the app

| Mode | URL |
|------|-----|
| Dev mode (React dev server) | http://localhost:3000 |
| Build mode (backend serves React) | http://127.0.0.1:8000 |

> The `package.json` has `"proxy": "http://127.0.0.1:8000"` so the React dev server automatically forwards `/api/*` requests to the backend.

---

### Option C — Electron desktop window

Run CiM as a native desktop app with the full Electron shell.

> **How it works on Mac (dev mode):** There is no pre-built `frontend/build`, so Electron is
> pointed at the **React dev server on port 3000**. Both the backend (port 8000) and the
> React dev server (port 3000) must be running before Electron launches.

#### One-click (recommended)

```bash
cd /Users/jayprakash/Desktop/CiM
bash start_cim_mac.sh --electron
```

This single command automatically:
1. Creates / activates the `.venv` Python virtualenv
2. Installs backend Python dependencies
3. Creates the database if missing
4. Starts the FastAPI backend on **port 8000**
5. Starts the React dev server on **port 3000**
6. Waits for both to be healthy
7. Launches the Electron desktop window pointing at `http://localhost:3000`

---

#### Manual (3 terminals)

**Terminal 1 — Backend**

```bash
cd /Users/jayprakash/Desktop/CiM
source .venv/bin/activate
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000 --log-level warning
```

Wait until you see the server start (no errors), then:

```bash
# Verify backend is up:
curl http://127.0.0.1:8000/api/health
# Expected: {"status":"ok", ...}
```

**Terminal 2 — React dev server**

```bash
cd /Users/jayprakash/Desktop/CiM/frontend
npm install       # first time only — installs node_modules
BROWSER=none npm start
```

Wait until you see `Compiled successfully!` in the terminal output.

**Terminal 3 — Electron**

```bash
cd /Users/jayprakash/Desktop/CiM/desktop
npm install       # first time only — installs Electron
CIM_URL="http://localhost:3000" npx electron .
```

The Charts In Motion desktop window will open and load the app.

> **Port summary:**
> | Service | Port | Started in |
> |---------|------|------------|
> | FastAPI backend | 8000 | Terminal 1 |
> | React dev server | 3000 | Terminal 2 |
> | Electron (desktop window) | — | Terminal 3 |

> **Important:** Always start Terminal 1 and Terminal 2 **before** Terminal 3.
> Electron will show a blank loading screen until both services are ready.

---

## 5. Stopping the App

### Using the stop script

```bash
bash stop_cim_mac.sh
```

This:
1. Calls the graceful `/api/admin/stop-all` endpoint
2. Kills processes by their saved PID files
3. Force-kills anything still on ports 8000 and 3000

### Manual stop

Press **Ctrl+C** in whichever terminal is running the server.  
Or kill by port:

```bash
# Kill backend (port 8000)
lsof -ti tcp:8000 | xargs kill -9

# Kill frontend dev server (port 3000)
lsof -ti tcp:3000 | xargs kill -9
```

---

## 6. Seeding Data

After the app is running you can reseed data at any time:

```bash
# From project root with venv active:
source .venv/bin/activate

# Recreate the dev database from scratch
python create_dev_db.py

# Reseed 2 years of OHLCV candles
python seed_ohlcv.py
```

For real NSE market data, the scraping scripts exist but require network access:

```bash
python scrape_daily.py        # scrape latest daily prices
python scrape_financials.py   # scrape financial data
python scrape_indices.py      # scrape index data
```

> **Note:** These scrapers pull from NSE / screener.in. Internet connection required.

---

## 7. Environment Variables

These are optional but useful:

| Variable | Default | Description |
|----------|---------|-------------|
| `CIM_URL` | `http://127.0.0.1:8000` | Override the URL Electron connects to |
| `CIM_DEV` | *(unset)* | Set to `1` to force "Dev" title in Electron |
| `CIM_DEV_TOOLS` | *(unset)* | Set to `1` to enable DevTools in packaged Electron |
| `NSE_PULSE_SMTP_HOST` | *(unset)* | SMTP host for feedback email |
| `NSE_PULSE_SMTP_PORT` | `587` | SMTP port |
| `NSE_PULSE_SMTP_USER` | *(unset)* | SMTP username |
| `NSE_PULSE_SMTP_PASS` | *(unset)* | SMTP password |
| `NSE_PULSE_FROM_EMAIL` | *(SMTP user)* | From address for feedback |

Set them in your shell profile (`~/.zshrc`):

```bash
export CIM_DEV=1
```

---

## 8. Troubleshooting

### "python3: command not found"

Install Python 3.11+:

```bash
brew install python@3.11
# Then use: python3.11 -m venv .venv
```

### "npm: command not found"

Install Node.js:

```bash
brew install node
```

### Backend starts but immediately crashes

Check the backend log:

```bash
cat runtime/logs/backend.log
```

Common causes:
- Missing Python package → run `pip install -r requirements_runtime.txt`
- Missing database → run `python create_dev_db.py`
- Port 8000 already in use → run `lsof -ti tcp:8000 | xargs kill -9`

### "Cannot load market_sectors: missing …"

The backend needs sibling modules in `server/`. Make sure you run uvicorn from the **project root** (not from inside `server/`):

```bash
# correct — from project root
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000

# wrong — do NOT cd into server/
cd server && uvicorn server:app   # this will break module paths
```

### React dev server shows blank page or API errors

- Make sure the backend is running on port 8000 **first**
- The React proxy (`"proxy": "http://127.0.0.1:8000"`) forwards all `/api/*` calls to backend
- Check browser console (F12) for CORS or 404 errors

### Electron window is blank or stuck

Electron needs **both** the backend (port 8000) and the React dev server (port 3000) running.
Check each:

```bash
# Is backend healthy?
curl http://127.0.0.1:8000/api/health

# Is React dev server up?
curl -I http://localhost:3000
```

If either fails, start it before launching Electron:

```bash
# Terminal 1
source .venv/bin/activate
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend && BROWSER=none npm start

# Terminal 3 — only after both above are up
cd desktop && CIM_URL="http://localhost:3000" npx electron .
```

If Electron is already open and blank, kill and relaunch Terminal 3 above.

### Port already in use

```bash
# Check what's on port 8000
lsof -i tcp:8000

# Force kill it
lsof -ti tcp:8000 | xargs kill -9
```

### Apple Silicon (M1/M2/M3) issues

Some Python packages may need native ARM builds. If you see architecture errors:

```bash
# Install Python natively for Apple Silicon via pyenv
brew install pyenv
pyenv install 3.11.9
pyenv local 3.11.9
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_runtime.txt
```

---

## 9. Running Tests

```bash
source .venv/bin/activate

# Backend unit tests
python -m unittest discover -s server/tests -p "test_*.py" -v
```

---

## 10. Building a Production Frontend

Build the React app so it's served by FastAPI (no separate React server needed):

```bash
cd frontend
npm run build
cd ..
```

This creates `frontend/build/`. Now start **only** the backend:

```bash
source .venv/bin/activate
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` — the backend serves the React build directly.

---

## Quick Reference Card

```bash
# ── SETUP (do once) ───────────────────────────────────────────────
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_runtime.txt
python create_dev_db.py
python seed_ohlcv.py
cd frontend && npm install && cd ..
cd desktop && npm install && cd ..     # installs Electron

# ── START — browser mode (simplest) ───────────────────────────────
bash start_cim_mac.sh
# Opens: http://localhost:3000

# ── START — Electron desktop mode (one-click) ─────────────────────
bash start_cim_mac.sh --electron
# Launches the native desktop window

# ── START — Electron mode (manual, 3 terminals) ───────────────────
# Terminal 1:
source .venv/bin/activate
python -m uvicorn server.server:app --host 127.0.0.1 --port 8000

# Terminal 2:
cd frontend && BROWSER=none npm start

# Terminal 3 (after both are up):
cd desktop && CIM_URL="http://localhost:3000" npx electron .

# ── STOP ──────────────────────────────────────────────────────────
bash stop_cim_mac.sh
# or: Ctrl+C in the terminal running start_cim_mac.sh

# ── LOGS ──────────────────────────────────────────────────────────
tail -f runtime/logs/backend.log
tail -f runtime/logs/frontend.log

# ── HEALTH CHECK ──────────────────────────────────────────────────
curl http://127.0.0.1:8000/api/health   # backend
curl -I http://localhost:3000            # React dev server
```

---

*Charts In Motion · CiM · NSE market analysis — Mac Guide*
