import {
  normalizeEarningsMarkerDate,
  resolveEarningsAnchorDate,
} from './earningsChartMarkers';

export const CORP_MARKER_TIMEFRAMES = new Set([
  '1D',
  '2D',
  '3D',
  '4D',
  '5D',
  '6D',
  '7D',
]);

export const SPLIT_MARKER_COLOR = '#a371f7';
export const DIVIDEND_MARKER_COLOR = '#d29922';

export function shouldShowCorpMarkers(timeframe) {
  return CORP_MARKER_TIMEFRAMES.has(String(timeframe || '').trim().toUpperCase());
}

export function normalizeCorpMarkerDate(value) {
  return normalizeEarningsMarkerDate(value);
}

export function buildAnchoredCorpMarkers(markers, barTimes) {
  return (markers || []).map((marker) => {
    const eventDate = normalizeCorpMarkerDate(marker?.date);
    if (!eventDate) return null;
    const chartAnchorDate = resolveEarningsAnchorDate(eventDate, barTimes);
    if (!chartAnchorDate) return null;
    const kind = String(marker?.kind || '').trim().toLowerCase();
    const label = kind === 'dividend' ? 'D' : 'S';
    const color = marker?.color || (kind === 'dividend' ? DIVIDEND_MARKER_COLOR : SPLIT_MARKER_COLOR);
    return {
      ...marker,
      date: eventDate,
      chart_anchor_date: chartAnchorDate,
      kind,
      label,
      color,
    };
  }).filter(Boolean);
}

export function buildCorpMarkerLookup(markers) {
  const lookup = new Map();
  for (const marker of buildAnchoredCorpMarkers(markers, [])) {
    lookup.set(marker.chart_anchor_date, marker);
  }
  return lookup;
}

export function buildBottomCorpMarkers(markers, barTimes, timeToCoordinate, width) {
  const visibleDates = new Set((barTimes || []).map(normalizeCorpMarkerDate).filter(Boolean));
  const anchored = buildAnchoredCorpMarkers(markers, barTimes);
  const out = [];
  for (const marker of anchored) {
    if (!visibleDates.has(marker.chart_anchor_date)) continue;
    const x = typeof timeToCoordinate === 'function'
      ? timeToCoordinate(marker.chart_anchor_date)
      : null;
    if (x == null) continue;
    if (typeof width === 'number' && (x < -16 || x > width + 16)) continue;
    const title = marker.kind === 'dividend'
      ? `Dividend ${marker.date}${marker.amount != null ? ` · ₹${Number(marker.amount).toFixed(2)}` : ''}`
      : `Split ${marker.date}${marker.ratio != null ? ` · ${marker.ratio}:1` : ''}`;
    out.push({
      id: `${marker.kind}:${marker.date}:${marker.chart_anchor_date}`,
      x,
      date: marker.chart_anchor_date,
      color: marker.color,
      label: marker.label,
      title,
      marker,
    });
  }
  out.sort((a, b) => a.date.localeCompare(b.date));
  return out;
}

export function mergeBottomChartMarkers(earningsMarkers, corpMarkers) {
  const merged = [...(earningsMarkers || []), ...(corpMarkers || [])];
  merged.sort((a, b) => String(a.date).localeCompare(String(b.date)));
  return merged;
}
