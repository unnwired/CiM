# INR and count display (CiM)

**Rule:** User-facing labels, table cells, placeholders, and subtitles use **Million / Billion / Trillion** only. **Never** show Cr, Crore, L, or Lakh in the UI.

---

## Monetary values (full INR from API/DB)

Use `formatMarketCap` or `formatINR` from `reference/formatMarketCap.js` (canonical: `packages/browser/src/utils/formatMarketCap.js`).

Examples: `₹12.34B`, `₹500.00M`, `₹1.20T`

---

## BSE quarterly_results (stored in crores)

Use `formatINRFromCrores()` — converts crores × 1e7 then applies M/B/T.

---

## Share volume / counts

Use `formatCompactCount()` → `12.34M`, `5.00B` (no ₹, no Cr/L).

---

## EPS per share

Plain rupee decimals (e.g. `12.50`), not M/B/T.

---

## Filter inputs

Users may type `M`, `B`, `T` (parsing may accept `Cr` internally). Never display parsed examples as `50B` placeholders that look like active filters unless intentional.

---

## Do not

- Add new `fmtCr`, `formatCr`, `1e7 + " Cr"`, or `" L"` display helpers in UI code.
- Use subtitles like "Figures in ₹ Cr."
