# CiM UI Standard (browser showcase)

**Authority:** All new or changed UI under `packages/browser/` must follow this document.  
**Enforcement:** `.cursor/rules/cim-ui-standard.mdc` (always applied for browser work).

---

## 1. Design tokens (only source)

Use CSS variables from `packages/browser/src/styles/global.css`. **Do not invent hex colors** in components.

| Token | Use |
|--------|-----|
| `--bg-primary` / `--bg-secondary` / `--bg-tertiary` | Surfaces |
| `--bg-hover` / `--bg-active` | Row hover, pressed |
| `--border` / `--border-light` | Dividers |
| `--text-primary` / `--text-secondary` / `--text-muted` | Text |
| `--accent-blue` | Primary actions |
| `--accent-green` / `--accent-red` | P&L, success, error |
| `--font-mono` | Prices, symbols, numeric columns |
| `--font-sans` | Labels, body |

---

## 2. Typography scale

| Role | Size | Weight |
|------|------|--------|
| Page / dialog title | 13px | 600 |
| Table body / form fields | 11–12px | 400 |
| Table header / footer | 11px | 400 |
| Muted helper / chip | 10px | 400 |
| Symbol tickers (mono) | 11px | 600 |

**Never** override `fontSize` on shared chrome helpers (buttons, footers) per call site.

---

## 3. Spacing scale

| Token | px | Use |
|--------|-----|-----|
| `INNER` | 4 | Label → control, inset lines |
| `GAP` | 8 | Form fields, footer button gap |
| `PANE` | 14–16 | Dialog padding |

P&L forms: `PNL_FORM_GAP = 8`, `PNL_FORM_INNER_GAP = 4` in `pnlFormDialogChrome.js`.  
Admin dialogs: `CIM_FORM_GAP = 8`, `CIM_FORM_INNER_GAP = 4` in `cimDialogChrome.js`.

---

## 4. Buttons (mandatory)

**P&L surfaces:** use `PnlDialogButton` / `PnlToolbarButton` (`pnlFormDialogChrome.js`).

**Admin / confirm / general modals:** use `CimDialogButton` (`cimDialogChrome.js`). No raw `<button style={...}>` with ad hoc padding.

**Grid row actions:** `PnlGridActionButton` (22px compact) for in-table actions (e.g. Book).

| Property | Value |
|----------|--------|
| Height | `28px` (`PNL_BTN_HEIGHT` / `CIM_BTN_HEIGHT`) |
| Padding | `0 12–14px` |
| Font | 11px, sans |
| Primary weight | 600 |
| `whiteSpace` | `nowrap` |
| `boxSizing` | `border-box` |

Variants:

| Variant | Use | Module |
|---------|-----|--------|
| `secondary` | Cancel, dismiss | `CimDialogButton`, `PnlDialogButton` |
| `primary` | Confirm, save, incremental update | same |
| `danger` | Destructive full rebuild, delete | `CimDialogButton` only |

Busy labels: `Importing…`, `Booking…`, `Starting…` — same width class; short idle labels (`Import`, `Book`, `Rebuild`).

**Dialog footers:** Use the dialog shell’s **`footer` prop** + footer style helper. Never put action buttons inside `children`.

**Wide dialogs** (import, filter rebuild): `CIM_DIALOG_WIDTH_WIDE` / `PNL_FORM_DIALOG_WIDTH_WIDE` (520 / 400px). Simple forms: `CIM_DIALOG_WIDTH` (420px) or `PNL_FORM_DIALOG_WIDTH` (252px).

---

## 5. Tables / grids

Use `stockTableChrome.js`:

- `STOCK_LIST_ROW_HEIGHT = 32`
- `STOCK_LIST_HEADER_HEIGHT = 36`
- `stockListGridTrackStyle` + `StockListGridCell` for aligned columns

**Symbol column:** `PnlSymbolCell` — fixed 14px drag slot + 10px chevron slot + label. Always reserve both slots on parent and child rows.

---

## 6. Dialogs

| Pattern | Module |
|---------|--------|
| P&L modal shell | `PnlFormDialog` (`pnlFormDialogChrome.js`) |
| Admin / confirm / filter rebuild | `CimFormDialog` + `CimDialogButton` (`cimDialogChrome.js`) |
| Book / Add / Import | P&L chrome; footer via `footer={...}` |
| Overlay click | Closes (unless busy — disable overlay close while submitting) |
| Esc | Must close (`CimFormDialog` handles this by default) |

**Chip toggles** (timeframe pickers, multi-select filters): `cimChipButtonStyle(active, disabled)` — do not invent one-off chip styles.

---

## 7. INR / counts

Per `.cursor/rules/inr-display-mbt.mdc`: M/B/T only in UI; use `formatMarketCap.js` helpers.

---

## 8. Before marking UI done

1. Run mental **polish-ui** checklist (shortcuts if bound, Esc on modals).
2. Footer buttons same height, one row or deliberate two-row layout (repair left, actions right).
3. No label wrapping on buttons — shorten label or widen dialog.
4. Reuse chrome modules; **do not duplicate** inline button styles.

---

## 9. Chrome module map

| Surface | File |
|---------|------|
| Admin / confirm dialogs + buttons | `components/cimDialogChrome.js` (`CimFormDialog`, `CimDialogButton`, `cimChipButtonStyle`) |
| P&L dialogs + buttons | `components/pnlFormDialogChrome.js` (`PnlDialogButton`, `PnlToolbarButton`, `PnlGridActionButton`) |
| P&L symbol column | `components/PnlSymbolCell.js` |
| Stock / P&L tables | `components/stockTableChrome.js` |
| Period / dates | `components/PnLDateSelect.js` |

---

*Last updated: 03 Sep 26*
