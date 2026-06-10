# Charts In Motion — updates

This repository is the **official update channel** for [Charts In Motion](https://github.com/unnwired/CiM-Updates) (CiM), the Windows desktop app for NSE equities and indices.

It contains **release packages only** — not application source code. Development and builds happen in the separate CiM source repository.

---

## For CiM users

If Charts In Motion is already installed on your PC (e.g. `D:\CiM`):

### Automatic (recommended)

1. Open **Settings** (cogwheel) → **Apply update**.
2. CiM also checks for updates in the background about every **90 minutes**.
3. When a newer release is available, confirm the prompt. The app downloads the package, applies it, and closes so you can restart with `start_cim.bat` or the desktop shortcut.

Your personal data is preserved: watchlists, portfolio, layouts, screener session, license file, and `nse_data.db` are **not** replaced by updates.

### Manual (USB or email from vendor)

1. Close Charts In Motion.
2. Extract `CiM-Update-{version}.zip` into your install folder’s `UPDATE` directory:

   ```text
   D:\CiM\UPDATE\CiM-Update-1.0.4\
   ```

3. Run `Install-Client-Update.bat` inside that folder.
4. Start Charts In Motion again.

If activation fails after an update, run `Repair-CiMLicense.bat` in your install folder and enter the install key from support.

---

## Releases on this repo

Each [GitHub Release](https://github.com/unnwired/CiM-Updates/releases) ships one asset:

| Item | Example |
|------|---------|
| **Tag** | `v1.0.4` |
| **Asset** | `CiM-Update-1.0.4.zip` |

CiM reads `config\github_updates.json` inside your install and compares the latest release version to local `version.txt`. Updates are offered only when the release is **newer**.

**Latest release:** use the [Releases](https://github.com/unnwired/CiM-Updates/releases) page — do not clone this repo expecting full application code.

---

## For vendors (publishing)

Build the update ZIP on the vendor machine from the CiM source repo:

```powershell
.\scripts\build_update_package.ps1 -Version 1.0.4
```

Upload `installer\output\CiM-Update-1.0.4.zip` to a new Release here:

- Tag: `v1.0.4`
- Title: e.g. `Charts In Motion 1.0.4`
- Attach: `CiM-Update-1.0.4.zip`
- Mark as **Latest**

Asset name must match `CiM-Update-{version}.zip` so the in-app updater can find it.

### Package contents (reference)

```text
CiM-Update-1.0.4/
├── update.manifest.json      # file list + SHA256 checksums
├── Install-Client-Update.bat
├── READ_ME_CLIENT.txt
└── payload/                  # files merged into the install folder
    ├── version.txt
    ├── server/...
    ├── frontend/build/...
    └── ...
```

---

## How the app checks for updates

1. **Local first** — `{install}\UPDATE\CiM-Update-*\` if a package is already on disk.
2. **GitHub second** — latest release on `unnwired/CiM-Updates`, asset `CiM-Update-*.zip`.

Download staging: `%LOCALAPPDATA%\CiM\update-staging\`  
Logs: `{install}\runtime\logs\update-download.log`, `update-apply.log`

---

## What does not belong in this repo

- Application source code (use the CiM development repository)
- Customer databases or license files
- Vendor build secrets
- Full installers (`CiMSetup-*.exe`) — those are distributed separately

---

## Support

For install keys, activation, or failed updates, contact Charts In Motion support with your **machine code** from `Repair-CiMLicense.bat` and relevant log files from `runtime\logs\`.

---

*Charts In Motion · CiM · NSE market analysis for Windows*
