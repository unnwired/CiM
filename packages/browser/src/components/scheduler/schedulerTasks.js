/** Single source of truth for Admin Scheduler task metadata. */

export const SCHEDULER_TASKS = [
  {
    key: 'ohlcv',
    label: 'Fetch chart data (OHLCV)',
    desc: 'Download/update raw daily bars into the database. This is chart data, not filter snapshots.',
    scheduleTypes: ['interval', 'daily', 'weekly'],
    defaultInterval: 30,
    defaultTime: '15:30',
    defaultWeekday: 4,
  },
  {
    key: 'filterRebuildDaily',
    label: 'Filter rebuild — daily incremental',
    desc: 'Incremental refresh of selected precomputed filter data for recently changed symbols.',
    scheduleTypes: ['daily'],
    defaultTime: '23:00',
    defaultWeekday: 4,
    defaultScheduleType: 'daily',
    defaultPreset: {
      keys: ['price_ohlc', 'ema', 'macd', 'stochrsi', 'avg_volume', 'range_channel'],
      mode: 'incremental',
      days_back: 1,
      timeframes: ['4H', '1D', '2D', '3D', '4D', '5D', '6D', '1W', '2W'],
    },
  },
  {
    key: 'filterRebuildWeekly',
    label: 'Filter rebuild — weekly full',
    desc: 'Full rebuild of selected precomputed filter data. Schedule off-peak.',
    scheduleTypes: ['weekly'],
    defaultTime: '02:00',
    defaultWeekday: 5,
    defaultScheduleType: 'weekly',
    defaultPreset: {
      keys: ['price_ohlc', 'ema', 'macd', 'stochrsi', 'avg_volume', 'range_channel'],
      mode: 'full',
      days_back: 1,
      timeframes: ['4H', '1D', '2D', '3D', '4D', '5D', '6D', '1W', '2W', '4W', '1M'],
    },
  },
  {
    key: 'eodReconcile',
    label: 'EOD bhavcopy reconcile',
    desc: 'Overlay screener price and 1D% from NSE bhavcopy.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '16:15',
    defaultWeekday: 4,
  },
  {
    key: 'liveQuotesWarm',
    label: 'Live NSE quotes warm',
    desc: 'Bulk NSE refresh for dashboard day-change.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '09:15',
    defaultWeekday: 4,
  },
  {
    key: 'splitWatch',
    label: 'Stock split watch',
    desc: 'Scan for splits and auto-apply adjustments.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '10:00',
    defaultWeekday: 4,
  },
  {
    key: 'earningsPlusWarm',
    label: 'Earnings+ cache warm',
    desc: 'Incremental refresh of earnings cache.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '11:00',
    defaultWeekday: 4,
  },
  {
    key: 'fetchFinancials',
    label: 'Fetch financials',
    desc: 'Update screener financial columns from Screener.in.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '02:00',
    defaultWeekday: 5,
  },
  {
    key: 'fetchScreenerSectors',
    label: 'Screener.in sector fill',
    desc: 'Fill empty industry labels from Screener.in.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '03:00',
    defaultWeekday: 5,
  },
  {
    key: 'expandUniverse',
    label: 'Expand screener universe',
    desc: 'Add new symbols to the screener table.',
    scheduleTypes: ['daily', 'weekly'],
    defaultTime: '04:00',
    defaultWeekday: 6,
  },
];

export const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const OHLCV_INTERVALS = [15, 30, 60, 90];

export const FILTER_REBUILD_TASK_KEYS = ['filterRebuildDaily', 'filterRebuildWeekly'];

export function isFilterRebuildTask(taskKey) {
  return FILTER_REBUILD_TASK_KEYS.includes(taskKey);
}

export function normalizeWeekdaysIst(value, fallback = 4) {
  if (Array.isArray(value) && value.length) {
    const days = [...new Set(value
      .map((d) => Number(d))
      .filter((d) => Number.isFinite(d))
      .map((d) => Math.max(0, Math.min(6, d))))].sort((a, b) => a - b);
    if (days.length) return days;
  }
  const rawSingle = Number(value ?? fallback);
  const single = Math.max(0, Math.min(6, Number.isFinite(rawSingle) ? rawSingle : Number(fallback) || 4));
  return [single];
}

export function toggleWeekday(weekdays, idx) {
  const set = new Set(normalizeWeekdaysIst(weekdays));
  if (set.has(idx)) {
    if (set.size === 1) return [...set];
    set.delete(idx);
  } else {
    set.add(idx);
  }
  return [...set].sort((a, b) => a - b);
}

export function formatWeekdaysSummary(weekdays) {
  return normalizeWeekdaysIst(weekdays).map((d) => WEEKDAY_LABELS[d] || 'Mon').join(', ');
}

export function taskMeta(key) {
  return SCHEDULER_TASKS.find((t) => t.key === key) || SCHEDULER_TASKS[0];
}

function normalizeScheduleTypeForTask(task, raw) {
  let st = raw === 'weekly' ? 'weekly' : raw === 'daily' ? 'daily' : 'interval';
  if (!task.scheduleTypes.includes(st)) {
    st = task.defaultScheduleType || task.scheduleTypes[0] || 'daily';
  }
  return st;
}

function normalizePresetForTask(task, preset) {
  if (!isFilterRebuildTask(task.key)) return undefined;
  const raw = preset || task.defaultPreset || {};
  const defaults = task.defaultPreset || {};
  const keys = Array.isArray(raw.keys) && raw.keys.length ? raw.keys : defaults.keys;
  const timeframes = Array.isArray(raw.timeframes) && raw.timeframes.length ? raw.timeframes : defaults.timeframes;
  return {
    keys: [...new Set((keys || []).map((k) => String(k || '').trim()).filter(Boolean))],
    mode: task.key === 'filterRebuildWeekly' ? 'full' : 'incremental',
    days_back: Math.max(0, Math.min(30, Number(raw.days_back ?? defaults.days_back ?? 1) || 1)),
    timeframes: [...new Set((timeframes || []).map((tf) => String(tf || '').trim().toUpperCase()).filter(Boolean))],
  };
}

export function defaultFormEntry(task) {
  const [h, m] = (task.defaultTime || '15:30').split(':');
  const base = {
    enabled: false,
    afterTime: task.defaultTime || '15:30',
    afterHourIst: parseInt(h, 10) || 15,
    afterMinuteIst: parseInt(m, 10) || 30,
    weekdayIst: task.defaultWeekday ?? 4,
    weekdaysIst: [task.defaultWeekday ?? 4],
  };
  if (task.key === 'ohlcv') {
    return {
      ...base,
      scheduleType: 'interval',
      intervalMinutes: task.defaultInterval ?? 30,
    };
  }
  const entry = {
    ...base,
    scheduleType: task.defaultScheduleType || 'daily',
  };
  const preset = normalizePresetForTask(task);
  return preset ? { ...entry, preset } : entry;
}

export function defaultForm() {
  const form = {};
  for (const t of SCHEDULER_TASKS) {
    form[t.key] = defaultFormEntry(t);
  }
  return form;
}

function timeFromCfg(cfg, fallback = '15:30') {
  const h = String(cfg?.afterHourIst ?? fallback.split(':')[0]).padStart(2, '0');
  const m = String(cfg?.afterMinuteIst ?? fallback.split(':')[1]).padStart(2, '0');
  return `${h}:${m}`;
}

function parseTimePart(value, fallback, min, max) {
  const parsed = parseInt(value, 10);
  const safe = Number.isFinite(parsed) ? parsed : fallback;
  return Math.max(min, Math.min(max, safe));
}

export function formFromConfig(config = {}) {
  const form = defaultForm();
  for (const task of SCHEDULER_TASKS) {
    const c = config[task.key] || {};
    const st = normalizeScheduleTypeForTask(task, c.scheduleType);
    form[task.key] = {
      enabled: !!c.enabled,
      scheduleType: st,
      afterTime: timeFromCfg(c, task.defaultTime),
      afterHourIst: Number(c.afterHourIst ?? 15),
      afterMinuteIst: Number(c.afterMinuteIst ?? 30),
      weekdayIst: Number(c.weekdayIst ?? task.defaultWeekday ?? 4),
      weekdaysIst: normalizeWeekdaysIst(
        c.weekdaysIst ?? (c.weekdayIst != null ? [c.weekdayIst] : [task.defaultWeekday ?? 4]),
      ),
      ...(task.key === 'ohlcv' ? { intervalMinutes: Number(c.intervalMinutes ?? 30) } : {}),
      ...(isFilterRebuildTask(task.key) ? { preset: normalizePresetForTask(task, c.preset) } : {}),
    };
  }
  return form;
}

export function buildConfigFromForm(form) {
  const out = {};
  for (const task of SCHEDULER_TASKS) {
    const f = form[task.key] || defaultFormEntry(task);
    const parts = String(f.afterTime || task.defaultTime || '15:30').split(':');
    const scheduleType = normalizeScheduleTypeForTask(task, f.scheduleType);
    const weekdaysIst = normalizeWeekdaysIst(f.weekdaysIst ?? f.weekdayIst ?? task.defaultWeekday ?? 4);
    const entry = {
      enabled: !!f.enabled,
      scheduleType,
      afterHourIst: parseTimePart(parts[0], 15, 0, 23),
      afterMinuteIst: parseTimePart(parts[1], 30, 0, 59),
      weekdaysIst,
      weekdayIst: weekdaysIst[0],
    };
    if (task.key === 'ohlcv') {
      entry.intervalMinutes = Number(f.intervalMinutes ?? 30);
    }
    if (isFilterRebuildTask(task.key)) {
      entry.preset = normalizePresetForTask(task, f.preset);
    }
    out[task.key] = entry;
  }
  return out;
}

export function scheduleSummary(taskKey, cfg) {
  const task = taskMeta(taskKey);
  const c = cfg || {};
  if (!c.enabled) return 'Disabled';
  if (taskKey === 'ohlcv') {
    const time = timeFromCfg(c, task.defaultTime);
    if (c.scheduleType === 'weekly') {
      return `${formatWeekdaysSummary(c.weekdaysIst ?? c.weekdayIst)} ${time} IST`;
    }
    if (c.scheduleType === 'daily') return `Daily ${time} IST`;
    return `Every ${c.intervalMinutes ?? 30} min`;
  }
  const time = timeFromCfg(c, task.defaultTime);
  if (c.scheduleType === 'weekly') {
    return `${formatWeekdaysSummary(c.weekdaysIst ?? c.weekdayIst)} ${time} IST`;
  }
  return `Daily ${time} IST`;
}

export function fmtIst(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: 'short',
    });
  } catch {
    return iso;
  }
}

const STATE_PREFIX = {
  filterRebuildDaily: 'FilterRebuildDaily',
  filterRebuildWeekly: 'FilterRebuildWeekly',
  eodReconcile: 'EodReconcile',
  liveQuotesWarm: 'LiveQuotesWarm',
  splitWatch: 'SplitWatch',
  earningsPlusWarm: 'EarningsPlusWarm',
  fetchFinancials: 'FetchFinancials',
  fetchScreenerSectors: 'FetchScreenerSectors',
  expandUniverse: 'ExpandUniverse',
};

export function lastRunLine(taskKey, state = {}) {
  if (taskKey === 'ohlcv') {
    return `Last: ${fmtIst(state.lastOhlcvAt)}${state.lastOhlcvTrigger ? ` · ${state.lastOhlcvTrigger}` : ''}`;
  }
  const prefix = STATE_PREFIX[taskKey] || taskKey;
  const at = state[`last${prefix}At`];
  const trig = state[`last${prefix}Trigger`];
  return `Last: ${fmtIst(at)}${trig ? ` · ${trig}` : ''}`;
}

export function filterPresetSummary(preset = {}) {
  const mode = preset.mode === 'full' ? 'full' : 'incremental';
  const keys = Array.isArray(preset.keys) ? preset.keys.length : 0;
  const tfs = Array.isArray(preset.timeframes) ? preset.timeframes : [];
  const tfLabel = tfs.length ? tfs.join(', ') : 'default timeframes';
  return `${mode} · ${keys || 'all'} data source(s) · ${tfLabel}`;
}
