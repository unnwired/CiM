# Charts In Motion (CiM)

**Charts In Motion** is an offline-first Windows desktop app for NSE equities and indices — charting, screeners, market breadth, earnings, watchlists, and portfolio tracking. The product runs locally: **Electron** shell, **FastAPI** backend, **React** frontend, **SQLite** database.

| Build | Window title | When |
|-------|----------------|------|
| **Development** | Charts In Motion Dev | This repo — `server\server.py` present, unencrypted sources |
| **Client install** | Charts In Motion | Packaged export / installer |

---

## Repository layout

```text
Charts In Motion/
├── frontend/              React UI (npm)
├── desktop/               Electron shell (npm)
├── server/                FastAPI app + workers
├── data/                  SQLite DB + user JSON (local; not in git)
├── config/                Product and update settings
├── scripts/               Build, export, installer, and update scripts
├── installer/             Inno Setup (CiM.iss)
├── docs/                  Guides and technical notes
├── start_cim.bat          One-click dev / local run
├── Build-CiM.ps1          Full distribution build pipeline
└── version.txt            App version
```

**Related repository:** [unnwired/CiM-Updates](https://github.com/unnwired/CiM-Updates) — published client update packages (`CiM-Update-{version}.zip`).

---

## Prerequisites

- **Windows 10/11**
- **Node.js 18+** and npm (frontend + desktop)
- **Python 3.11** (development)
- **Inno Setup 6** (installer compile) — [jrsoftware.org](https://jrsoftware.org/isinfo.php)

Distribution builds require additional private configuration on the maintainer machine. That material is not documented in this public README.

---

## Run locally (development)

```bat
start_cim.bat
```

- With `frontend\build` present → backend at `http://127.0.0.1:8000` + Electron
- Without a build → `npm start` dev server on port 3000

Stop: `stop_cim.bat`

More detail: [README_START_STOP.md](README_START_STOP.md)

---

## Build a release

```powershell
.\Build-CiM.ps1
```

Outputs are written locally under `installer\output\` (gitignored): export tree, Windows installer, and update ZIP.

**Smoke test** (on the export tree):

```powershell
.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"
```

Publish client updates to [CiM-Updates Releases](https://github.com/unnwired/CiM-Updates/releases) with tag `v{version}`.

---

## Configuration

| File | Purpose |
|------|---------|
| `config\product.json` | Product name, slug, update repo, install defaults |
| `config\github_updates.json` | Update poll interval, asset naming |
| `version.txt` | Semver shown in UI and update checks |

---

## Tests

```powershell
python -m unittest discover -s server/tests -p "test_*.py" -v
python scripts\test_github_updates.py
```

---

## What not to commit

See [.gitignore](.gitignore). In short: local databases, user data, build output, dependencies, and any credentials or private configuration.

---

## Documentation

| Doc | Audience |
|-----|----------|
| [README_START_STOP.md](README_START_STOP.md) | Start/stop and local run |
| [docs/UPDATE.md](docs/UPDATE.md) | Client update flow |
| [docs/CLIENT_UPDATE.md](docs/CLIENT_UPDATE.md) | End-user update steps |

---

## Stack

| Layer | Technology |
|-------|------------|
| Desktop | Electron |
| API | FastAPI + uvicorn |
| UI | React |
| Data | SQLite |
| Installer | Inno Setup |

---

*Charts In Motion · CiM · NSE market analysis for Windows*
