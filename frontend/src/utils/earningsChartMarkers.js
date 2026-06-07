export const EARNINGS_MARKER_TIMEFRAMES = new Set([
  '1D',
  '2D',
  '3D',
  '4D',
  '5D',
  '6D',
  '7D',
]);

export const EARNINGS_MARKER_BEAT_COLOR = '#2ea043';
export const EARNINGS_MARKER_MISS_COLOR = '#f85149';
export const EARNINGS_MARKER_STATUS_COLOR = '#d29922';

export function shouldShowEarningsMarkers(timeframe) {
  return EARNINGS_MARKER_TIMEFRAMES.has(String(timeframe || '').trim().toUpperCase());
}

export function normalizeEarningsMarkerDate(value) {
  if (value == null) return '';
  if (typeof value === 'object' && value.year != null && value.month != null && value.day != null) {
    const month = String(value.month).padStart(2, '0');
    const day = String(value.day).padStart(2, '0');
    return `${value.year}-${month}-${day}`;
  }
  const text = String(value);
  return text.length >= 10 ? text.slice(0, 10) : text;
}

export function getEarningsMarkerColor(outcomeKind) {
  return outcomeKind === 'beat' ? EARNINGS_MARKER_BEAT_COLOR : EARNINGS_MARKER_MISS_COLOR;
}

export function getEarningsModalVariant(outcomeKind) {
  return outcomeKind === 'beat' ? 'beat' : 'reported_miss';
}

export function normalizeEarningsComparisonStatus(value) {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'verified' || status === 'provisional' || status === 'discrepancy' || status === 'unverified') {
    return status;
  }
  return 'unverified';
}

export function getEarningsStatusLabel(status) {
  if (status === 'provisional') return 'Provisional';
  if (status === 'discrepancy') return 'Mismatch';
  if (status === 'unverified') return 'Unverified';
  return '';
}

export function resolveEarningsAnchorDate(releaseDate, barTimes) {
  const normalizedReleaseDate = normalizeEarningsMarkerDate(releaseDate);
  if (!normalizedReleaseDate) return '';
  const normalizedBarDates = (barTimes || [])
    .map(normalizeEarningsMarkerDate)
    .filter(Boolean);
  if (normalizedBarDates.includes(normalizedReleaseDate)) return normalizedReleaseDate;
  let previousBarDate = '';
  for (const barDate of normalizedBarDates) {
    if (barDate >= normalizedReleaseDate) break;
    previousBarDate = barDate;
  }
  return previousBarDate;
}

export function buildAnchoredEarningsEvents(events, barTimes) {
  return (events || []).map((event) => {
    const earningsReleaseDate = normalizeEarningsMarkerDate(event?.earnings_release_date);
    if (!earningsReleaseDate) return null;
    const chartAnchorDate = resolveEarningsAnchorDate(earningsReleaseDate, barTimes);
    if (!chartAnchorDate) return null;
    return {
      ...event,
      earnings_release_date: earningsReleaseDate,
      chart_anchor_date: chartAnchorDate,
    };
  }).filter(Boolean);
}

export function buildEarningsEventLookup(events) {
  const lookup = new Map();
  for (const event of events || []) {
    const earningsReleaseDate = normalizeEarningsMarkerDate(event?.earnings_release_date);
    const chartAnchorDate = normalizeEarningsMarkerDate(event?.chart_anchor_date) || earningsReleaseDate;
    if (!earningsReleaseDate || !chartAnchorDate) continue;
    const outcomeKind = event?.outcome_kind === 'beat' ? 'beat' : 'miss';
    lookup.set(chartAnchorDate, {
      ...event,
      earnings_release_date: earningsReleaseDate,
      chart_anchor_date: chartAnchorDate,
      outcome_kind: outcomeKind,
      comparison_status: normalizeEarningsComparisonStatus(event?.comparison_status),
    });
  }
  return lookup;
}

export function buildBottomEarningsMarkers(events, barTimes, timeToCoordinate, width) {
  const visibleDates = new Set((barTimes || []).map(normalizeEarningsMarkerDate).filter(Boolean));
  const markers = [];
  for (const event of buildEarningsEventLookup(events).values()) {
    if (!visibleDates.has(event.chart_anchor_date)) continue;
    const x = typeof timeToCoordinate === 'function'
      ? timeToCoordinate(event.chart_anchor_date)
      : null;
    if (x == null) continue;
    if (typeof width === 'number' && (x < -16 || x > width + 16)) continue;
    markers.push({
      id: `earnings:${event.earnings_release_date}:${event.chart_anchor_date}`,
      x,
      date: event.chart_anchor_date,
      color: getEarningsMarkerColor(event.outcome_kind),
      event,
    });
  }
  markers.sort((a, b) => a.date.localeCompare(b.date));
  return markers;
}
