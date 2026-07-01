/** MACD histogram chain fields — optional add-on to Level/Signal MACD filters. */

export const HISTOGRAM_SIDE_OPTIONS = [
  { key: 'positive', label: 'Positive', desc: 'Bars above zero (zero below)' },
  { key: 'negative', label: 'Negative', desc: 'Bars below zero (zero above)' },
];

export const HISTOGRAM_CHAIN_MODE_OPTIONS = [
  { key: 'increasing', label: 'Increasing', desc: 'Each bar farther from zero (−1→−2 or +1→+2)' },
  { key: 'receding', label: 'Receding', desc: 'Each bar closer to zero (−3→−2→−1)' },
];

export function normalizeHistogramSide(side) {
  if (side === 'negative') return 'negative';
  return 'positive';
}

export function normalizeChainMode(mode) {
  if (mode === 'receding') return 'receding';
  return 'increasing';
}

export function parseAllowCrossZero(value) {
  if (value === true || value === 1 || value === '1' || value === 'true') return true;
  return false;
}

export function isHistChainEnabled(f) {
  if (!f) return false;
  if (f.filter_type === 'macd_hist_chain') return true;
  if (f.source === 'histogram') return true;
  return f.hist_chain_enabled === true || f.hist_chain_enabled === 1 || f.hist_chain_enabled === '1';
}

/** Legacy histogram-only presets (no Level/Signal condition). */
export function isHistChainOnly(f) {
  if (!f) return false;
  if (f.filter_type === 'macd_hist_chain') return true;
  if (f.source === 'histogram') return true;
  return f.hist_chain_only === true || f.hist_chain_only === 1 || f.hist_chain_only === '1';
}

export function macdFilterInitialValues(raw) {
  const init = raw || {};
  if (init.filter_type === 'macd_hist_chain' || init.source === 'histogram') {
    return {
      ...init,
      filter_type: 'macd',
      source: init.source === 'signal' ? 'signal' : 'macd',
      hist_chain_enabled: true,
      hist_chain_only: init.filter_type === 'macd_hist_chain' || init.source === 'histogram',
      condition: init.condition || 'above',
      target: init.target || 'signal',
      target_value: init.target_value ?? 0,
    };
  }
  if (isHistChainEnabled(init)) {
    return { ...init, hist_chain_enabled: true };
  }
  return init;
}

export function buildMacdHistogramSuffix(f) {
  const mode = f.chain_mode === 'increasing' ? 'increasing' : 'receding';
  const side = f.histogram_side === 'positive' ? 'pos' : 'neg';
  const parts = [
    'Hist',
    mode,
    `${f.bars_to_compare ?? 4} bars`,
    `str ${f.allowed_stragglers ?? 0}`,
    side,
  ];
  if (f.allow_cross_zero) {
    const crossPrefix = mode === 'increasing' ? 'before' : 'after';
    parts.push(`cross ${crossPrefix} ${f.cross_zero_bars ?? 3}`);
    parts.push(`cz str ${f.cross_zero_stragglers ?? 0}`);
  }
  return parts.join(' · ');
}

export function buildMacdHistogramFilterLabel(f) {
  return `MACD Histogram (${f.timeframe}) · ${buildMacdHistogramSuffix(f)}`;
}

export function buildMacdCombinedFilterLabel(f) {
  if (isHistChainOnly(f) && isHistChainEnabled(f)) {
    return buildMacdHistogramFilterLabel(f);
  }
  const srcLabel = f.source === 'signal' ? 'MACD Signal' : 'MACD Level';
  const condLabel = {
    above: '>',
    above_eq: '≥',
    below: '<',
    below_eq: '≤',
    crosses_up: '↑✕',
    crosses_down: '↓✕',
    above_pct: `>${f.pct_value}%`,
    below_pct: `<${f.pct_value}%`,
  }[f.condition] || '>';
  const tgtLabel = f.target === 'value'
    ? String(f.target_value)
    : f.target === 'macd'
      ? 'MACD Level'
      : 'MACD Signal';
  const linePart = `${srcLabel} (${f.timeframe}) ${condLabel} ${tgtLabel}`;
  if (!isHistChainEnabled(f)) return linePart;
  return `${linePart} · ${buildMacdHistogramSuffix(f)}`;
}
