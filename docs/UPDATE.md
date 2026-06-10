# Charts In Motion updates

**Clients:** see **[CLIENT_UPDATE.md](CLIENT_UPDATE.md)** — steps run only on your install PC, not the developer machine.

Updates never replace your personal data files:

- `data\watchlists.json`
- `data\portfolio.json`
- `data\layout.json`
- `data\saved_filters.json`
- `data\screener_session.json`
- `data\screener_profile\`

## In the app (recommended)

1. Open **Settings** (cogwheel) → **Apply update**.
2. Charts In Motion checks for an update in this order:
   - **Local:** `CiM\UPDATE\CiM-Update-{version}\update.manifest.json` and `payload\` (also supports a flat `UPDATE\update.manifest.json` layout).
   - **GitHub:** latest release on [unnwired/cim-updates](https://github.com/unnwired/cim-updates) (`CiM-Update-{version}.zip`).
3. While Charts In Motion is open, it also checks GitHub every **90 minutes** (configurable in `config\github_updates.json`). If a newer release exists, you get a popup asking whether to update.
4. Confirm when prompted. For GitHub updates, Charts In Motion downloads the ZIP, extracts it into `UPDATE\`, then applies files from the manifest, updates `version.txt`, and closes the app.
5. Start Charts In Motion again with `start_cim.bat` or the desktop shortcut.

## Manual local update folder

Your vendor may ship `CiM-Update-{version}\` containing:

- `update.manifest.json`
- `payload\` (mirror of paths inside the install folder)

Extract the vendor ZIP into your install `UPDATE` folder:

```text
D:\CiM\UPDATE\CiM-Update-1.0.4\
```

Example:

```text
CiM\UPDATE\CiM-Update-1.0.4\update.manifest.json
CiM\UPDATE\CiM-Update-1.0.4\payload\server\...
CiM\UPDATE\CiM-Update-1.0.4\payload\frontend\build\...
```

Run `Install-Client-Update.bat` inside the extracted folder (no typing paths).

## GitHub releases (vendor)

1. Run `Build-CiM.ps1` — produces `installer\output\CiM-Update-{version}\` and `CiM-Update-{version}.zip`.
2. Create a GitHub Release on [unnwired/cim-updates](https://github.com/unnwired/cim-updates) with tag `v{version}` and upload the ZIP as a release asset.
3. Clients on a build with GitHub support can use **Apply update** or wait for the 90-minute background prompt.

Configuration: `config\github_updates.json` (`owner`, `repo`, `checkIntervalMinutes`, `backgroundCheckEnabled`).

## After an update

Encrypted app builds clear the decrypt cache automatically. If startup fails, contact support with `runtime\logs\update-apply.log`.
