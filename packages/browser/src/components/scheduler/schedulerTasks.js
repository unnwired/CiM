/** Single source of truth for Admin Scheduler task metadata. */

export const FILTER_REBUILD_KEY = 'filterRebuild';

export const FILTER_DEFAULT_KEYS = [
  'price_ohlc',
  'ema',
  'macd',
  'stochrsi',
  'avg_volume',
  'range_channel',
];

export const FILTER_LIGHT_TIMEFRAMES = ['30m', '4H', '1D', '2D', '3D', '4D', '5D', '6D', '1W', '2W'];

export const FILTER_FULL_TIMEFRAMES = [...FILTER_LIGHT_TIMEFRAMES, '4W', '1M'];

/** Keep ``30m`` lowercase so save/validate never treat it as month ``30M``. */
export function normalizeSnapshotTimeframe(raw) {
  const tf = String(raw || '').trim();
  if (!tf) return '';
  if (tf.toLowerCase() === '30m') return '30m';
  return tf.toUpperCase();
}

export const FILTER_REBUILD_TASK_META = {
  key: FILTER_REBUILD_KEY,
  label: 'Filter rebuild',
  desc: 'Rebuild precomputed filter snapshots (price OHLC, EMA, MACD, StochRSI, avg volume, range channel, etc.). Add multiple schedules at different times. Daily every day, Weekly on chosen days, or Monthly on the first chosen weekday of each month.',
  scheduleTypes: ['daily', 'weekly', 'monthly'],
  defaultScheduleType: 'weekly',
  defaultTime: '23:00',
  defaultWeekday: 0,
};

export const SCHEDULER_TASKS = [
  {
    key: 'ohlcv',
    label: 'Fetch chart data (OHLCV)',
    desc: 'Download/update daily bars, then 4H and 30m after 15:30 IST (mid-session skips full 4H/30m; live 4H uses quote overlay). Upstox primary. You can schedule this task more than once (e.g. 15:35 and 16:20).',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultScheduleType: 'daily',
    defaultTime: '15:30',
    defaultWeekday: 4,
  },
  {
    key: 'eodReconcile',
    label: 'EOD bhavcopy reconcile',
    desc: 'Overlay screener price and 1D% from NSE bhavcopy.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '16:15',
    defaultWeekday: 4,
  },
  {
    key: 'liveQuotesWarm',
    label: 'Live NSE quotes warm',
    desc: 'Bulk NSE refresh for dashboard day-change.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '09:15',
    defaultWeekday: 4,
  },
  {
    key: 'splitWatch',
    label: 'Stock split watch',
    desc: 'Scan for splits and auto-apply adjustments.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '10:00',
    defaultWeekday: 4,
  },
  {
    key: 'earningsPlusWarm',
    label: 'Earnings+ cache warm',
    desc: 'Incremental refresh of earnings cache.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '11:00',
    defaultWeekday: 4,
  },
  {
    key: 'earningsTvResync',
    label: 'TV earnings re-sync (recent)',
    desc: 'Re-pull TradingView reported EPS/revenue for symbols that reported in the last 4 days (one market scan). Picks up TV corrections without scanning the full universe. Add multiple daily times if you want morning + afternoon passes.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultScheduleType: 'daily',
    defaultTime: '12:00',
    defaultWeekday: 4,
  },
  {
    key: 'fetchFinancials',
    label: 'Fetch financials',
    desc: 'Update screener financial columns from Screener.in.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '02:00',
    defaultWeekday: 5,
  },
  {
    key: 'fetchScreenerSectors',
    label: 'Screener.in sector fill',
    desc: 'Fill empty industry labels from Screener.in.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '03:00',
    defaultWeekday: 5,
  },
  {
    key: 'expandUniverse',
    label: 'Expand screener universe',
    desc: 'Add new symbols to the screener table.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '04:00',
    defaultWeekday: 6,
  },
  {
    key: 'mfNav',
    label: 'AMFI mutual fund NAVs',
    desc: 'Download open-ended scheme NAVs from AMFI after market close only (blocked before 15:30 IST; not part of live Update).',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultTime: '21:30',
    defaultWeekday: 4,
  },
  {
    key: 'sectorIndexCores',
    label: 'Refresh sector index cores',
    desc: 'Re-fetch Nifty sector/theme constituents (Auto, Energy, Consumption, Chemicals, Banks, …) into the Market Sector index∪industry cache. Weekly after rebalances is enough; monthly also fine.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultScheduleType: 'weekly',
    defaultTime: '05:00',
    defaultWeekday: 6,
  },
  {
    key: 'exchangeClassification',
    label: 'Sync exchange industry labels',
    desc: 'Refresh screener nse_sector / nse_industry from exchange classification CSVs so Market Sector industry expansion stays current when companies move or labels change.',
    scheduleTypes: ['daily', 'weekly', 'monthly'],
    defaultScheduleType: 'weekly',
    defaultTime: '05:30',
    defaultWeekday: 6,
  },
];

export const EDITOR_TASK_OPTIONS = [
  FILTER_REBUILD_TASK_META,
  ...SCHEDULER_TASKS,
];

export const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function isFilterRebuildKey(key) {
  return key === FILTER_REBUILD_KEY || String(key || '').startsWith('filter:');
}

export function isTaskScheduleKey(key) {
  return String(key || '').startsWith('task:');
}

export function filterSelectionId(selectedKey) {
  if (!selectedKey) return null;
  if (selectedKey.startsWith('filter:')) return selectedKey.slice(7);
  return null;
}

export function taskSelectionId(selectedKey) {
  if (!selectedKey) return null;
  if (selectedKey.startsWith('task:')) return selectedKey.slice(5);
  return null;
}

export function newTaskScheduleId() {
  return `ts_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
}

export function newTaskSchedule(taskKey = 'ohlcv') {
  const task = taskMeta(taskKey) || SCHEDULER_TASKS[0];
  const key = task.key;
  const entry = defaultFormEntry(task);
  return {
    id: newTaskScheduleId(),
    taskKey: key,
    name: '',
    enabled: false,
    scheduleType: entry.scheduleType,
    afterTime: entry.afterTime,
    afterHourIst: entry.afterHourIst,
    afterMinuteIst: entry.afterMinuteIst,
    weekdaysIst: entry.weekdaysIst,
    weekdayIst: entry.weekdayIst,
  };
}

export function taskScheduleFromEntry(entry) {
  const raw = entry || {};
  const taskKey = String(raw.taskKey || raw.task || 'ohlcv').trim();
  const task = taskMeta(taskKey) || SCHEDULER_TASKS[0];
  const st = normalizeScheduleTypeForTask(task, raw.scheduleType);
  let weekdaysIst = Array.isArray(raw.weekdaysIst)
    ? normalizeWeekdaysIst(raw.weekdaysIst, task.defaultWeekday ?? 4, true)
    : normalizeWeekdaysIst(raw.weekdayIst, task.defaultWeekday ?? 4, true);
  if (st === 'monthly' && weekdaysIst.length > 1) weekdaysIst = [weekdaysIst[0]];
  if (st === 'daily') weekdaysIst = [0, 1, 2, 3, 4, 5, 6];
  const h = String(raw.afterHourIst ?? (task.defaultTime || '15:30').split(':')[0]).padStart(2, '0');
  const m = String(raw.afterMinuteIst ?? (task.defaultTime || '15:30').split(':')[1]).padStart(2, '0');
  return {
    id: raw.id || newTaskScheduleId(),
    taskKey: task.key,
    name: typeof raw.name === 'string' ? raw.name : '',
    enabled: !!raw.enabled,
    scheduleType: st,
    afterTime: `${h}:${m}`,
    afterHourIst: Number(raw.afterHourIst ?? parseInt(h, 10)),
    afterMinuteIst: Number(raw.afterMinuteIst ?? parseInt(m, 10)),
    weekdaysIst,
    weekdayIst: weekdaysIst[0] ?? (task.defaultWeekday ?? 4),
  };
}

export function taskScheduleToConfig(draft) {
  const task = taskMeta(draft.taskKey) || SCHEDULER_TASKS[0];
  const scheduleType = normalizeScheduleTypeForTask(task, draft.scheduleType);
  const hasNumeric = Number.isFinite(Number(draft.afterHourIst)) && Number.isFinite(Number(draft.afterMinuteIst));
  const timeStr = draft.afterTime
    || (hasNumeric
      ? `${String(draft.afterHourIst).padStart(2, '0')}:${String(draft.afterMinuteIst).padStart(2, '0')}`
      : (task.defaultTime || '15:30'));
  const parts = String(timeStr).split(':');
  let weekdaysIst = Array.isArray(draft.weekdaysIst)
    ? normalizeWeekdaysIst(draft.weekdaysIst, task.defaultWeekday ?? 4, true)
    : normalizeWeekdaysIst(draft.weekdayIst, task.defaultWeekday ?? 4, true);
  if (scheduleType === 'daily') weekdaysIst = [0, 1, 2, 3, 4, 5, 6];
  else if (scheduleType === 'monthly') {
    weekdaysIst = weekdaysIst.length ? [weekdaysIst[0]] : [];
  }
  return {
    id: draft.id || newTaskScheduleId(),
    taskKey: task.key,
    name: typeof draft.name === 'string' ? draft.name.trim() : '',
    enabled: !!draft.enabled,
    scheduleType,
    afterHourIst: parseTimePart(parts[0], 15, 0, 23),
    afterMinuteIst: parseTimePart(parts[1], 30, 0, 59),
    weekdaysIst,
    weekdayIst: weekdaysIst[0] ?? (task.defaultWeekday ?? 4),
  };
}

export function taskLastRunLine(entryId, state = {}) {
  const at = state[`taskSchedule:${entryId}:lastAt`];
  const trig = state[`taskSchedule:${entryId}:trigger`];
  return `Last: ${fmtIst(at)}${trig ? ` · ${trig}` : ''}`;
}

export function newFilterScheduleId() {
  return `fs_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
}

export function normalizeFilterScheduleType(raw, weekdaysIst) {
  const st = String(raw || '').trim().toLowerCase();
  if (st === 'daily' || st === 'weekly' || st === 'monthly') return st;
  // Legacy entries had no scheduleType: all 7 days meant "daily".
  const days = Array.isArray(weekdaysIst) ? weekdaysIst : [];
  return days.length === 7 ? 'daily' : 'weekly';
}

export function newFilterSchedule() {
  // Nothing is selected by default: the operator picks frequency, sources, and
  // timeframes explicitly (no pre-checked items to undo).
  return {
    id: newFilterScheduleId(),
    enabled: false,
    mode: 'incremental',
    scheduleType: 'weekly',
    afterTime: '23:00',
    afterHourIst: 23,
    afterMinuteIst: 0,
    weekdaysIst: [],
    weekdayIst: 0,
    preset: {
      keys: [],
      mode: 'incremental',
      days_back: 1,
      timeframes: [],
    },
  };
}

export function filterScheduleFromEntry(entry) {
  const raw = entry || {};
  const mode = raw.mode === 'full' || raw.preset?.mode === 'full' ? 'full' : 'incremental';
  const preset = raw.preset || {};
  const [fh, fm] = (FILTER_REBUILD_TASK_META.defaultTime || '23:00').split(':');
  const h = String(raw.afterHourIst ?? fh).padStart(2, '0');
  const m = String(raw.afterMinuteIst ?? fm).padStart(2, '0');
  // Preserve an explicit empty weekday list; only fall back to a legacy single
  // weekday when weekdaysIst was never provided as an array.
  const weekdaysIst = Array.isArray(raw.weekdaysIst)
    ? normalizeWeekdaysIst(raw.weekdaysIst, 0, true)
    : normalizeWeekdaysIst(raw.weekdayIst, 0, true);
  const scheduleType = normalizeFilterScheduleType(raw.scheduleType, weekdaysIst);
  return {
    id: raw.id || newFilterScheduleId(),
    enabled: !!raw.enabled,
    mode,
    scheduleType,
    afterTime: `${h}:${m}`,
    afterHourIst: Number(raw.afterHourIst ?? fh),
    afterMinuteIst: Number(raw.afterMinuteIst ?? fm),
    weekdaysIst,
    weekdayIst: weekdaysIst[0] ?? 0,
    preset: {
      keys: Array.isArray(preset.keys) ? preset.keys : [],
      mode,
      days_back: Math.max(0, Math.min(30, Number(preset.days_back ?? 1) || 1)),
      timeframes: Array.isArray(preset.timeframes) ? preset.timeframes : [],
    },
  };
}

export function filterScheduleToConfig(draft) {
  const mode = draft.mode === 'full' ? 'full' : 'incremental';
  // Prefer explicit numeric hour/minute (backend-synced entries have these but
  // no afterTime string); only fall back to afterTime, then the 23:00 default.
  // Without this, re-saving a synced entry would silently reset it to 11 PM.
  const hasNumeric = Number.isFinite(Number(draft.afterHourIst)) && Number.isFinite(Number(draft.afterMinuteIst));
  const timeStr = draft.afterTime
    || (hasNumeric
      ? `${String(draft.afterHourIst).padStart(2, '0')}:${String(draft.afterMinuteIst).padStart(2, '0')}`
      : '23:00');
  const parts = String(timeStr).split(':');
  const weekdaysIst = Array.isArray(draft.weekdaysIst)
    ? normalizeWeekdaysIst(draft.weekdaysIst, 0, true)
    : normalizeWeekdaysIst(draft.weekdayIst, 0, true);
  const scheduleType = normalizeFilterScheduleType(draft.scheduleType, weekdaysIst);
  const normalizedDays = scheduleType === 'daily'
    ? [0, 1, 2, 3, 4, 5, 6]
    : scheduleType === 'monthly'
      ? (weekdaysIst.length ? [weekdaysIst[0]] : [])
      : weekdaysIst;
  return {
    id: draft.id || newFilterScheduleId(),
    enabled: !!draft.enabled,
    mode,
    scheduleType,
    afterHourIst: parseTimePart(parts[0], 23, 0, 23),
    afterMinuteIst: parseTimePart(parts[1], 0, 0, 59),
    weekdaysIst: normalizedDays,
    weekdayIst: normalizedDays[0] ?? 0,
    preset: {
      keys: [...new Set((draft.preset?.keys || []).map((k) => String(k || '').trim()).filter(Boolean))],
      mode,
      days_back: Math.max(0, Math.min(30, Number(draft.preset?.days_back ?? 1) || 1)),
      timeframes: [...new Set(
        (draft.preset?.timeframes || [])
          .map((tf) => normalizeSnapshotTimeframe(tf))
          .filter(Boolean),
      )],
    },
  };
}

export function filterScheduleSummary(entry, options = {}) {
  const c = entry || {};
  const modeLabel = (c.mode === 'full' || c.preset?.mode === 'full') ? 'Full' : 'Incremental';
  const time = timeFromCfg(c, FILTER_REBUILD_TASK_META.defaultTime);
  const days = normalizeWeekdaysIst(c.weekdaysIst ?? c.weekdayIst, 4, true);
  const scheduleType = normalizeFilterScheduleType(c.scheduleType, days);
  let freq;
  if (scheduleType === 'daily') freq = `Daily ${time} IST`;
  else if (scheduleType === 'monthly') {
    freq = days.length
      ? `First ${WEEKDAY_LABELS[days[0]] || 'Mon'} of month ${time} IST`
      : `No day · ${time} IST`;
  } else if (days.length === 0) freq = `No days · ${time} IST`;
  else freq = `${formatWeekdaysSummary(days)} ${time} IST`;
  const keys = Array.isArray(c.preset?.keys) ? c.preset.keys.length : 0;
  const sourceLabel = keys ? `${keys} source(s)` : 'no sources';
  return `${freq} · ${modeLabel} · ${sourceLabel}`;
}

export function filterLastRunLine(entryId, state = {}) {
  const at = state[`filterSchedule:${entryId}:lastAt`];
  const trig = state[`filterSchedule:${entryId}:trigger`];
  return `Last: ${fmtIst(at)}${trig ? ` · ${trig}` : ''}`;
}

export function normalizeWeekdaysIst(value, fallback = 4, allowEmpty = false) {
  if (Array.isArray(value)) {
    const days = [...new Set(value
      .map((d) => Number(d))
      .filter((d) => Number.isFinite(d))
      .map((d) => Math.max(0, Math.min(6, d))))].sort((a, b) => a - b);
    if (days.length) return days;
    // An explicit (possibly empty) array is honored as empty when allowed.
    if (allowEmpty) return [];
  }
  if (allowEmpty && (value === undefined || value === null)) return [];
  const rawSingle = Number(value ?? fallback);
  const single = Math.max(0, Math.min(6, Number.isFinite(rawSingle) ? rawSingle : Number(fallback) || 4));
  return [single];
}

export function toggleWeekday(weekdays, idx) {
  // No minimum: the list may be cleared to empty (unselected by default).
  const set = new Set(normalizeWeekdaysIst(weekdays, 4, true));
  if (set.has(idx)) set.delete(idx);
  else set.add(idx);
  return [...set].sort((a, b) => a - b);
}

/** Monthly frequency: exactly one weekday (first that day of the month). */
export function selectSingleWeekday(weekdays, idx) {
  const current = normalizeWeekdaysIst(weekdays, 4, true);
  if (current.length === 1 && current[0] === idx) return [];
  return [idx];
}

export function formatWeekdaysSummary(weekdays) {
  return normalizeWeekdaysIst(weekdays).map((d) => WEEKDAY_LABELS[d] || 'Mon').join(', ');
}

export function taskMeta(key) {
  if (isFilterRebuildKey(key)) return FILTER_REBUILD_TASK_META;
  return SCHEDULER_TASKS.find((t) => t.key === key) || SCHEDULER_TASKS[0];
}

function normalizeScheduleTypeForTask(task, raw) {
  const st = String(raw || '').trim().toLowerCase();
  // Legacy OHLCV interval schedules become daily.
  if (st === 'interval') {
    return task.scheduleTypes.includes('daily') ? 'daily' : (task.scheduleTypes[0] || 'daily');
  }
  if (task.scheduleTypes.includes(st)) return st;
  return task.defaultScheduleType || task.scheduleTypes[0] || 'daily';
}

export function defaultFormEntry(task) {
  const [h, m] = (task.defaultTime || '15:30').split(':');
  return {
    enabled: false,
    afterTime: task.defaultTime || '15:30',
    afterHourIst: parseInt(h, 10) || 15,
    afterMinuteIst: parseInt(m, 10) || 30,
    weekdayIst: task.defaultWeekday ?? 4,
    weekdaysIst: [task.defaultWeekday ?? 4],
    scheduleType: task.defaultScheduleType || 'daily',
  };
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
    let weekdaysIst = normalizeWeekdaysIst(
      c.weekdaysIst ?? (c.weekdayIst != null ? [c.weekdayIst] : [task.defaultWeekday ?? 4]),
    );
    if (st === 'monthly' && weekdaysIst.length > 1) {
      weekdaysIst = [weekdaysIst[0]];
    }
    form[task.key] = {
      enabled: !!c.enabled,
      scheduleType: st,
      afterTime: timeFromCfg(c, task.defaultTime),
      afterHourIst: Number(c.afterHourIst ?? 15),
      afterMinuteIst: Number(c.afterMinuteIst ?? 30),
      weekdayIst: weekdaysIst[0] ?? (task.defaultWeekday ?? 4),
      weekdaysIst,
    };
  }
  return form;
}

export function buildConfigFromForm(form, filterSchedules = [], taskSchedules = []) {
  const out = {};
  for (const task of SCHEDULER_TASKS) {
    // Legacy singleton stubs — always disabled; execution uses taskSchedules.
    const f = form[task.key] || defaultFormEntry(task);
    const parts = String(f.afterTime || task.defaultTime || '15:30').split(':');
    const scheduleType = normalizeScheduleTypeForTask(task, f.scheduleType);
    let weekdaysIst = normalizeWeekdaysIst(f.weekdaysIst ?? f.weekdayIst ?? task.defaultWeekday ?? 4);
    if (scheduleType === 'monthly') {
      weekdaysIst = weekdaysIst.length ? [weekdaysIst[0]] : [task.defaultWeekday ?? 4];
    } else if (scheduleType === 'daily') {
      weekdaysIst = [0, 1, 2, 3, 4, 5, 6];
    }
    out[task.key] = {
      enabled: false,
      scheduleType,
      afterHourIst: parseTimePart(parts[0], 15, 0, 23),
      afterMinuteIst: parseTimePart(parts[1], 30, 0, 59),
      weekdaysIst,
      weekdayIst: weekdaysIst[0],
    };
  }
  out.filterSchedules = (filterSchedules || []).map((s) => filterScheduleToConfig(s));
  out.taskSchedules = (taskSchedules || []).map((s) => taskScheduleToConfig(s));
  return out;
}

export function scheduleSummary(taskKey, cfg) {
  const task = taskMeta(taskKey);
  const c = cfg || {};
  if (!c.enabled) return 'Disabled';
  const time = timeFromCfg(c, task.defaultTime);
  if (c.scheduleType === 'monthly') {
    const day = normalizeWeekdaysIst(c.weekdaysIst ?? c.weekdayIst, task.defaultWeekday ?? 4)[0];
    return `First ${WEEKDAY_LABELS[day] || 'Mon'} of month ${time} IST`;
  }
  if (c.scheduleType === 'weekly') {
    return `${formatWeekdaysSummary(c.weekdaysIst ?? c.weekdayIst)} ${time} IST`;
  }
  return `Daily ${time} IST`;
}

export function fmtIst(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      day: '2-digit',
      month: 'short',
    });
  } catch {
    return iso;
  }
}

const STATE_PREFIX = {
  eodReconcile: 'EodReconcile',
  liveQuotesWarm: 'LiveQuotesWarm',
  splitWatch: 'SplitWatch',
  earningsPlusWarm: 'EarningsPlusWarm',
  earningsTvResync: 'EarningsTvResync',
  fetchFinancials: 'FetchFinancials',
  fetchScreenerSectors: 'FetchScreenerSectors',
  expandUniverse: 'ExpandUniverse',
  mfNav: 'MfNav',
  sectorIndexCores: 'SectorIndexCores',
  exchangeClassification: 'ExchangeClassification',
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
