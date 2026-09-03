# CiM Lovable Design — GitHub package

**Repo:** [unnwired/CiM](https://github.com/unnwired/CiM)  
**Purpose:** Everything Lovable (or an external UI designer) needs to extend the **Charts In Motion** browser showcase without breaking product conventions.

**Live app code** remains in `packages/browser/`. This folder is the **design contract + reference snapshots** for handoff.

---

## Start here

| # | File | Read for |
|---|------|----------|
| 1 | [LOVABLE_DESIGN_HANDOFF.md](LOVABLE_DESIGN_HANDOFF.md) | App shell, navigation, pages, charts, UX rules |
| 2 | [CIM_UI_STANDARD.md](CIM_UI_STANDARD.md) | Buttons, dialogs, tables, spacing (mandatory) |
| 3 | [INR_DISPLAY.md](INR_DISPLAY.md) | ₹M / ₹B / ₹T formatting — never Cr/L in UI |

---

## Reference snapshots (`reference/`)

Copies of production sources at handoff time. **Canonical sources** are under `packages/browser/src/` — sync these when tokens or chrome change materially.

| Path | Canonical source |
|------|------------------|
| `reference/global.css` | `packages/browser/src/styles/global.css` |
| `reference/formatMarketCap.js` | `packages/browser/src/utils/formatMarketCap.js` |
| `reference/chrome/cimDialogChrome.js` | `packages/browser/src/components/cimDialogChrome.js` |
| `reference/chrome/pnlFormDialogChrome.js` | `packages/browser/src/components/pnlFormDialogChrome.js` |
| `reference/chrome/stockTableChrome.js` | `packages/browser/src/components/stockTableChrome.js` |

---

## Scope

| In scope | Out of scope |
|----------|----------------|
| `packages/browser/` UI | `packages/desktop/` (Electron) |
| Web showcase testbed port **8002** | Live `D:\CiM\Client` (8001) unless owner approves |
| Dark theme, existing tokens | New color systems without owner sign-off |

---

## Verify after design changes

```powershell
cd packages\browser
npm test -- --watchAll=false
.\scripts\Deploy-CiMShowcaseFromRepo.ps1 -RestartShowcase
# http://127.0.0.1:8002 — hard refresh Ctrl+Shift+R
```

---

*Last updated: 03 Sep 26*
