# P&L Import — Implementation Plan (shipped 27 Jun 26)

Reference for support and future agents. Cursor plan file is the source during development; this copy lives in-repo.

## Problem

Tradebook CSV alone cannot represent bonus/split (TRENT 1:2) or same-day sells (PARAS, SUPREMEIND, VGUARD). CiM needed a client-scalable import path — not per-user ledger edits.

## Three-file contract

| File | Scope | CiM use |
|------|--------|---------|
| **Tradebook** | Historical executed trades | FIFO replay → closed + open |
| **Holdings** | Current delivery open snapshot | Reconcile open qty + avg |
| **Positions** | Today only (Kite Positions tab) | Book today's buys/sells via FIFO |

Pipeline order: tradebook → corp actions → holdings reconcile → today's positions.

## Modules

- `packages/server/zerodha_holdings.py`
- `packages/server/zerodha_positions.py`
- `packages/server/corp_actions.py`
- `data/corp_actions.json` (TRENT 1:2, record 2026-06-04)
- `packages/server/zerodha_import.py` — `run_zerodha_import_pipeline`

## API flags

| Flag | Default | Behavior |
|------|---------|----------|
| `reconcile_holdings` | true when holdings present | Open qty/avg from holdings |
| `import_todays_positions` | false | Apply Positions CSV rows |
| `apply_corp_actions` | true | Registry bonus/split on open lots |
| `validate_positions_pnl` | true | Broker P&L in preview |

Standalone: `POST /api/pnl/import/zerodha/holdings` (no tradebook re-import).

## E2E gate (mandatory before promote)

```powershell
.\scripts\Test-PnlImportGate.ps1
```

Layers: unit tests → `test_pnl_import_e2e.py` → `Test-CiMPnlImportE2E.ps1` on Client_Test :8002.

## Acceptance

- TRENT open qty **25** after holdings or corp action
- PARAS sell **18** today from Positions CSV
- Re-import positions: dedupe (no duplicate closed row)
- Book action: column sort mode preserved (layout fix in `PnLPage.js`)

See `docs/handoff/PROJECT_HANDOFF.md` §3.23 for file map and deploy workflow.
