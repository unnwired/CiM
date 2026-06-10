# Charts In Motion (CiM)

**Charts In Motion** is an offline-first Windows desktop app for NSE equities and indices — charting, screeners, market breadth, earnings, watchlists, and portfolio tracking. The product runs locally: **Electron** shell, **FastAPI** backend, **React** frontend, **SQLite** database.

| Build | Window title | When |
|-------|----------------|------|
| **Development** | Charts In Motion Dev `1.0.3` | This repo — `server\server.py` present, unencrypted sources |
| **Client install** | Charts In Motion `1.0.3` | Packaged export / installer — encrypted bytecode + JS |

---

## Repository layout

```text
Charts In Motion/          ← you are here (development root)
├── frontend/              React UI (npm)
├── desktop/               Electron shell (npm)
├── server/                FastAPI app + workers
├── data/                  SQLite DB + user JSON (local; not in git)
├── config/                product.json, github_updates.json
├── scripts/               Build, encrypt, installer, update, license tools
├── installer/             Inno Setup (CiM.iss)
├── docs/                  Client update guides, technical notes
├── start_cim.bat          One-click dev / local run
├── Build-CiM.ps1          Full distribution build (export → encrypt → installer)
└── version.txt            App version (sync with installer\output\version.txt for releases)
```

**Related repository:** [unnwired/CiM-Updates](https://github.com/unnwired/CiM-Updates) — **client update ZIPs only** (`CiM-Update-{version}.zip`). This repo is the **source and build system**; [unnwired/CiM](https://github.com/unnwired/CiM) is where development happens.

---

## Prerequisites

- **Windows 10/11**
- **Node.js 18+** and npm (frontend + desktop)
- **Python 3.11** (dev) or use embedded runtime after export
- **Inno Setup 6** (installer compile) — [jrsoftware.org](https://jrsoftware.org/isinfo.php)
- Vendor license secret on the build machine: `config\.build_license_secret` (see `config\build_license_secret.example`; **never commit**)

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

## Build a client release

Full pipeline (export, encrypt, installer, update ZIP):

```powershell
.\Build-CiM.ps1
```

Outputs (local, gitignored under `installer\output\`):

| Artifact | Path |
|----------|------|
| Export tree | `installer\output\CiM\` |
| Windows installer | `installer\output\CiMSetup-{version}.exe` |
| Update package | `installer\output\CiM-Update-{version}.zip` |

**Verify before shipping:**

```powershell
.\scripts\Test-CiMPackagedSmoke.ps1 -InstallRoot "installer\output\CiM"
```

Must show **PACKAGED SMOKE PASS** (health, SPA shell, JS bundle, stocks API, chart data).

Full gate (build + silent install + smoke):

```powershell
.\scripts\Run-CiMFullGate.ps1 -InstallDir D:\CiM -Version 1.0.3
```

Publish the update ZIP to [CiM-Updates Releases](https://github.com/unnwired/CiM-Updates/releases) with tag `v{version}`.

---

## Licensing (distribution)

- Clients activate with **machine code + install key** (offline).
- **Install keys** are minted on the vendor build PC only:

  ```powershell
  .\scripts\Generate-CiMInstallKey.ps1 -MachineCode <CLIENT_MACHINE_CODE>
  ```

- Client installs use embedded `server\_cim_dist_embedded.py` — **no** plaintext vendor secret in the shipped package.
- `Repair-CiMLicense-Auto.bat` is disabled; support issues keys manually.

---

## Configuration

| File | Purpose |
|------|---------|
| `config\product.json` | Product name, slug, GitHub update repo, install defaults |
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

See [.gitignore](.gitignore). In short:

- `data\nse_data.db` and user `data\*.json`
- `runtime\`, `node_modules\`, `frontend\build\`, `installer\output\`

---

## Documentation

| Doc | Audience |
|-----|----------|
| [USER_REQUIREMENTS.md](USER_REQUIREMENTS.md) | Product owner / agent verification bar |
| [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) | Full technical architecture and runbooks |
| [docs/UPDATE.md](docs/UPDATE.md) | In-app and manual client updates |
| [docs/CLIENT_UPDATE.md](docs/CLIENT_UPDATE.md) | End-user update steps |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

---

## Stack summary

| Layer | Technology |
|-------|------------|
| Desktop | Electron (`desktop/`) |
| API | FastAPI + uvicorn (`server/`) |
| UI | React (`frontend/`) |
| Data | SQLite (`data/nse_data.db`) |
| Installer | Inno Setup (`installer/CiM.iss`) |
| Distribution | Encrypted `.pyc.enc` / `.js.enc`, app-cache decrypt at runtime |

---

*Charts In Motion · CiM · NSE market analysis for Windows*
