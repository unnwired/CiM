/** Sort / summarize Market Map constituents for grid + treemap display. */

function finitePct(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Match server major / alpha sort — used after live overlay re-ranks tiles. */
export function sortMarketMapConstituents(rows, sort, alphaDesc = false) {
  const list = [...(rows || [])];
  if (sort === 'alpha') {
    list.sort((a, b) => String(a.symbol || '').localeCompare(String(b.symbol || '')));
    if (alphaDesc) list.reverse();
    return list;
  }
  list.sort((a, b) => {
    const ap = finitePct(a.change_pct);
    const bp = finitePct(b.change_pct);
    if (ap == null && bp == null) return String(a.symbol || '').localeCompare(String(b.symbol || ''));
    if (ap == null) return 1;
    if (bp == null) return -1;
    if (bp !== ap) return bp - ap;
    return String(a.symbol || '').localeCompare(String(b.symbol || ''));
  });
  return list;
}

export function summarizeConstituentChanges(rows) {
  const withChg = (rows || []).filter((r) => finitePct(r.change_pct) != null);
  const advances = withChg.filter((r) => finitePct(r.change_pct) > 0).length;
  const declines = withChg.filter((r) => finitePct(r.change_pct) < 0).length;
  const unchanged = withChg.filter((r) => finitePct(r.change_pct) === 0).length;
  const total = withChg.length || (rows || []).length;
  const pct_positive = withChg.length
    ? Math.round((advances / withChg.length) * 1000) / 10
    : null;
  return { advances, declines, unchanged, total, pct_positive };
}
