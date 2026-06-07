# FlowX update (client PC)

## What support sends

A ZIP of **`FlowX-Update-{version}`** on [GitHub Releases](https://github.com/unnwired/flowx-updates/releases), or the same folder/ZIP sent directly.

## Client steps (automatic — recommended)

1. Keep FlowX running (or open it).
2. When an update is available on GitHub, FlowX shows a popup every ~90 minutes (or use **Settings → Apply update** anytime).
3. Click **OK** to update. FlowX downloads the release ZIP, extracts it into `UPDATE\`, applies the update, and closes.
4. Start FlowX again with **`start_flowx.bat`**.

## Client steps (manual)

1. Close FlowX.
2. Download **`FlowX-Update-{version}.zip`** from GitHub Releases (or from support).
3. Extract into your FlowX **`UPDATE`** folder:

   ```
   D:\FlowX\UPDATE\FlowX-Update-1.0.4\
   ```

4. Double-click **`Install-Client-Update.bat`** inside that folder. Install path is detected automatically — no typing.
5. If prompted about license, run:

   ```powershell
   cd "<FlowX install folder>"
   powershell -ExecutionPolicy Bypass -File ".\scripts\Repair-FlowXLicense.ps1"
   ```

6. Run **`start_flowx.bat`** from the install folder.

## Success checks

| File | Location |
|------|----------|
| `update-result.txt` | Install root |
| `UPDATE\FlowX-Update-{version}\update.manifest.json` | Under install |
| `data\.flowx-license` | Under install |
| `Apply-Update.bat` | Install root (copied automatically) |

## Do not

- Run `Apply-Update.bat` from inside `UPDATE\payload` (wrong folder).
- Put the update in the FlowX root instead of `UPDATE\` (use `UPDATE\FlowX-Update-*`).

## If it fails

Send support:

- `runtime\logs\update-apply.log`
- `runtime\logs\update-download.log`
- `runtime\logs\backend-startup.err.log`
