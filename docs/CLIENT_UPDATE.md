# Charts In Motion update (client PC)

## What support sends

A ZIP of **`CiM-Update-{version}`** on [GitHub Releases](https://github.com/unnwired/cim-updates/releases), or the same folder/ZIP sent directly.

## Client steps (automatic — recommended)

1. Keep Charts In Motion running (or open it).
2. When an update is available on GitHub, Charts In Motion shows a popup every ~90 minutes (or use **Settings → Apply update** anytime).
3. Click **OK** to update. Charts In Motion downloads the release ZIP, extracts it into `UPDATE\`, applies the update, and closes.
4. Start Charts In Motion again with **`start_cim.bat`**.

## Client steps (manual)

1. Close Charts In Motion.
2. Download **`CiM-Update-{version}.zip`** from GitHub Releases (or from support).
3. Extract into your Charts In Motion **`UPDATE`** folder:

   ```
   D:\CiM\UPDATE\CiM-Update-1.0.4\
   ```

4. Double-click **`Install-Client-Update.bat`** inside that folder. Install path is detected automatically — no typing.
5. If prompted about license, run:

   ```powershell
   cd "<Charts In Motion install folder>"
   powershell -ExecutionPolicy Bypass -File ".\scripts\Repair-CiMLicense.ps1"
   ```

6. Run **`start_cim.bat`** from the install folder.

## Success checks

| File | Location |
|------|----------|
| `update-result.txt` | Install root |
| `UPDATE\CiM-Update-{version}\update.manifest.json` | Under install |
| `data\.cim-license` | Under install |
| `Apply-Update.bat` | Install root (copied automatically) |

## Do not

- Run `Apply-Update.bat` from inside `UPDATE\payload` (wrong folder).
- Put the update in the Charts In Motion root instead of `UPDATE\` (use `UPDATE\CiM-Update-*`).

## If it fails

Send support:

- `runtime\logs\update-apply.log`
- `runtime\logs\update-download.log`
- `runtime\logs\backend-startup.err.log`
