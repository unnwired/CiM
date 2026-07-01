import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  CIM_DIALOG_WIDTH_WIDE,
  CIM_FORM_INNER_GAP,
  CimDialogButton,
  CimFormDialog,
  cimChipButtonStyle,
  cimSectionLabelStyle,
} from './cimDialogChrome';
import EnabledSchedulersList from './scheduler/EnabledSchedulersList';
import IstTimeInput from './scheduler/IstTimeInput';
import { FIELD_HEIGHT, activeSchedulesViewportStyle } from './scheduler/schedulerFieldStyles';
import {
  WEEKDAY_LABELS,
  formatWeekdaysSummary,
  normalizeWeekdaysIst,
  toggleWeekday,
} from './scheduler/schedulerTasks';

const API = '';

function toggleInList(list, value) {
  const set = new Set(list);
  if (set.has(value)) set.delete(value);
  else set.add(value);
  return [...set];
}

function defaultKeys(options) {
  return (options?.items || []).map((it) => it.key);
}

function fullTimeframes(options) {
  return options?.snapshot_timeframes || [];
}

function lightTimeframes(options) {
  return fullTimeframes(options).filter((tf) => !['4W', '1M'].includes(tf));
}

function timeFromConfig(cfg, fallback) {
  const [fh, fm] = fallback.split(':');
  const h = String(cfg?.afterHourIst ?? fh).padStart(2, '0');
  const m = String(cfg?.afterMinuteIst ?? fm).padStart(2, '0');
  return `${h}:${m}`;
}

function presetFromConfig(cfg, fallbackKeys, fallbackTimeframes) {
  const preset = cfg?.preset || {};
  return {
    keys: Array.isArray(preset.keys) && preset.keys.length ? preset.keys : fallbackKeys,
    timeframes: Array.isArray(preset.timeframes) && preset.timeframes.length ? preset.timeframes : fallbackTimeframes,
  };
}

function ScheduleToggle({ enabled, disabled, onChange, label, detail }) {
  return (
    <label style={{
      display: 'flex',
      gap: 8,
      alignItems: 'flex-start',
      cursor: disabled ? 'not-allowed' : 'pointer',
      color: 'var(--text-primary)',
      opacity: disabled ? 0.65 : 1,
      fontSize: 12,
    }}
    >
      <input
        type="checkbox"
        checked={enabled}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        style={{ marginTop: 2 }}
      />
      <span>
        <strong>{label}</strong>
        <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: 10, marginTop: 2 }}>
          {detail}
        </span>
      </span>
    </label>
  );
}

const tabButtonBaseStyle = {
  border: 'none',
  borderRadius: 5,
  padding: '0 10px',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  flex: 1,
  minWidth: 0,
  height: FIELD_HEIGHT,
  boxSizing: 'border-box',
  borderStyle: 'solid',
  borderWidth: 1,
};

function ScheduleTypeTabs({ active, disabled, onSelect }) {
  const tabs = [
    { key: 'daily', label: 'Daily' },
    { key: 'weekly', label: 'Weekly' },
  ];
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
      {tabs.map((tab) => {
        const selected = active === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            disabled={disabled}
            aria-pressed={selected}
            onClick={() => onSelect(tab.key)}
            style={{
              ...tabButtonBaseStyle,
              backgroundColor: selected ? 'var(--accent-blue)' : 'var(--bg-primary)',
              color: selected ? '#fff' : 'var(--text-secondary)',
              borderColor: 'var(--border)',
              cursor: disabled ? 'not-allowed' : 'pointer',
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

function WeekdayChips({ weekdays, disabled, onToggle }) {
  const selected = new Set(normalizeWeekdaysIst(weekdays, 5));
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {WEEKDAY_LABELS.map((label, idx) => {
        const active = selected.has(idx);
        return (
          <button
            key={label}
            type="button"
            disabled={disabled}
            aria-pressed={active}
            title={active && selected.size === 1 ? 'At least one weekday required' : `Toggle ${label}`}
            onClick={() => onToggle(idx)}
            style={cimChipButtonStyle(active, disabled)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function DataSourcePicker({ options, selectedKeys, onToggle, disabled }) {
  return (
    <div>
      <div style={cimSectionLabelStyle}>Data sources</div>
      {(options.items || []).map((it) => (
        <label
          key={it.key}
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: CIM_FORM_INNER_GAP + 4,
            fontSize: 12,
            marginBottom: 6,
            cursor: disabled ? 'not-allowed' : 'pointer',
            color: 'var(--text-primary)',
          }}
        >
          <input
            type="checkbox"
            checked={selectedKeys.includes(it.key)}
            onChange={() => onToggle(it.key)}
            disabled={disabled}
            style={{ marginTop: 2 }}
          />
          <span>
            {it.label}
            {it.canonical_params ? (
              <span style={{ display: 'block', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                Canonical: {it.canonical_params.timeframe}, {it.canonical_params.lookback_bars} bars
              </span>
            ) : null}
          </span>
        </label>
      ))}
    </div>
  );
}

function TimeframePicker({ label, timeframes, selected, onToggle, disabled }) {
  return (
    <div>
      <div style={cimSectionLabelStyle}>{label}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {timeframes.map((tf) => {
          const active = selected.includes(tf);
          return (
            <button
              key={tf}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onToggle(tf)}
              style={cimChipButtonStyle(active, disabled)}
            >
              {tf}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function FilterRebuildDialog({
  open,
  onClose,
}) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [options, setOptions] = useState(null);
  const [scheduleStatus, setScheduleStatus] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [activeScheduleType, setActiveScheduleType] = useState('daily');

  const [dailyEnabled, setDailyEnabled] = useState(false);
  const [dailyTime, setDailyTime] = useState('23:00');
  const [dailyKeys, setDailyKeys] = useState([]);
  const [dailyTimeframes, setDailyTimeframes] = useState([]);

  const [weeklyEnabled, setWeeklyEnabled] = useState(false);
  const [weeklyTime, setWeeklyTime] = useState('02:00');
  const [weeklyWeekdays, setWeeklyWeekdays] = useState([5]);
  const [weeklyKeys, setWeeklyKeys] = useState([]);
  const [weeklyTimeframes, setWeeklyTimeframes] = useState([]);

  const syncFromPayload = useCallback((opts, schedules) => {
    const keys = defaultKeys(opts);
    const light = lightTimeframes(opts);
    const full = fullTimeframes(opts);
    const cfg = schedules?.config || {};
    const dailyCfg = cfg.filterRebuildDaily || {};
    const weeklyCfg = cfg.filterRebuildWeekly || {};
    const dailyPreset = presetFromConfig(dailyCfg, keys, light);
    const weeklyPreset = presetFromConfig(weeklyCfg, keys, full);

    setDailyEnabled(!!dailyCfg.enabled);
    setDailyTime(timeFromConfig(dailyCfg, '23:00'));
    setDailyKeys(dailyPreset.keys);
    setDailyTimeframes(dailyPreset.timeframes);
    setWeeklyEnabled(!!weeklyCfg.enabled);
    setWeeklyTime(timeFromConfig(weeklyCfg, '02:00'));
    setWeeklyWeekdays(normalizeWeekdaysIst(weeklyCfg.weekdaysIst ?? weeklyCfg.weekdayIst, 5));
    setWeeklyKeys(weeklyPreset.keys);
    setWeeklyTimeframes(weeklyPreset.timeframes);
  }, []);

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const [optionsRes, schedulesRes] = await Promise.all([
        axios.get(`${API}/api/admin/filter-rebuild/options`),
        axios.get(`${API}/api/admin/schedules`),
      ]);
      const opts = optionsRes.data || {};
      const schedules = schedulesRes.data || {};
      setOptions(opts);
      setScheduleStatus(schedules);
      syncFromPayload(opts, schedules);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to load filter schedules.');
    } finally {
      setLoading(false);
    }
  }, [open, syncFromPayload]);

  useEffect(() => {
    load();
  }, [load]);

  const timeframeOptions = useMemo(() => fullTimeframes(options), [options]);
  const activeScheduleCount = useMemo(() => {
    const config = scheduleStatus?.config || {};
    return Object.keys(config).filter((key) => config[key]?.enabled).length;
  }, [scheduleStatus]);

  const buildFilterTask = useCallback((taskKey) => {
    const enabled = taskKey === 'filterRebuildDaily' ? dailyEnabled : weeklyEnabled;
    const time = taskKey === 'filterRebuildDaily' ? dailyTime : weeklyTime;
    const [h, m] = String(time).split(':');
    const keys = taskKey === 'filterRebuildDaily' ? dailyKeys : weeklyKeys;
    const tfs = taskKey === 'filterRebuildDaily' ? dailyTimeframes : weeklyTimeframes;
    const weekdays = taskKey === 'filterRebuildDaily' ? [4] : normalizeWeekdaysIst(weeklyWeekdays, 5);
    return {
      enabled,
      scheduleType: taskKey === 'filterRebuildDaily' ? 'daily' : 'weekly',
      afterHourIst: Math.max(0, Math.min(23, parseInt(h, 10) || 0)),
      afterMinuteIst: Math.max(0, Math.min(59, parseInt(m, 10) || 0)),
      weekdayIst: weekdays[0],
      weekdaysIst: weekdays,
      preset: {
        keys,
        mode: taskKey === 'filterRebuildDaily' ? 'incremental' : 'full',
        days_back: 1,
        timeframes: tfs,
      },
    };
  }, [
    dailyEnabled,
    dailyKeys,
    dailyTime,
    dailyTimeframes,
    weeklyEnabled,
    weeklyKeys,
    weeklyTime,
    weeklyTimeframes,
    weeklyWeekdays,
  ]);

  const handleSave = useCallback(async () => {
    if (!dailyKeys.length && dailyEnabled) {
      setError('Select at least one daily filter data source, or disable the daily schedule.');
      return;
    }
    if (!weeklyKeys.length && weeklyEnabled) {
      setError('Select at least one weekly filter data source, or disable the weekly schedule.');
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const latest = await axios.get(`${API}/api/admin/schedules`);
      const nextConfig = {
        ...(latest.data?.config || {}),
        filterRebuildDaily: buildFilterTask('filterRebuildDaily'),
        filterRebuildWeekly: buildFilterTask('filterRebuildWeekly'),
      };
      const res = await axios.put(`${API}/api/admin/schedules`, nextConfig);
      setScheduleStatus(res.data || null);
      setMessage('Filter data schedule saved.');
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to save filter data schedule.');
    } finally {
      setSaving(false);
    }
  }, [
    buildFilterTask,
    dailyEnabled,
    dailyKeys.length,
    weeklyEnabled,
    weeklyKeys.length,
  ]);

  const handleClose = useCallback(() => {
    if (!saving) onClose?.();
  }, [onClose, saving]);

  const config = scheduleStatus?.config || {};
  const nextRuns = scheduleStatus?.nextRuns || {};
  const state = scheduleStatus?.state || {};
  const disabled = loading || saving;
  const showingDaily = activeScheduleType === 'daily';
  const selectedEnabled = showingDaily ? dailyEnabled : weeklyEnabled;
  const selectedTime = showingDaily ? dailyTime : weeklyTime;
  const selectedKeys = showingDaily ? dailyKeys : weeklyKeys;
  const selectedTimeframes = showingDaily ? dailyTimeframes : weeklyTimeframes;
  const setSelectedEnabled = showingDaily ? setDailyEnabled : setWeeklyEnabled;
  const setSelectedTime = showingDaily ? setDailyTime : setWeeklyTime;
  const setSelectedKeys = showingDaily ? setDailyKeys : setWeeklyKeys;
  const setSelectedTimeframes = showingDaily ? setDailyTimeframes : setWeeklyTimeframes;
  const selectedTitle = showingDaily ? 'Daily filter refresh' : 'Weekly full filter refresh';
  const selectedDetail = showingDaily
    ? 'Incremental rebuild for recently changed symbols.'
    : 'Full rebuild for the selected weekdays and time.';

  return (
    <CimFormDialog
      open={open}
      title="Schedule filter data"
      subtitle="Choose daily and weekly schedules for precomputed filter data. Active schedules below are shared with Admin Scheduler so timings stay synced."
      titleId="filter-rebuild-title"
      width={CIM_DIALOG_WIDTH_WIDE}
      onClose={handleClose}
      closeOnOverlay={!saving}
      error={error}
      footer={(
        <>
          <CimDialogButton onClick={handleClose} disabled={saving}>
            Cancel
          </CimDialogButton>
          <CimDialogButton
            variant="primary"
            onClick={handleSave}
            disabled={disabled}
          >
            {saving ? 'Saving...' : 'Save schedule'}
          </CimDialogButton>
        </>
      )}
    >
      {loading && <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0 }}>Loading schedule...</p>}
      {!loading && options && (
        <>
          <div>
            <div style={cimSectionLabelStyle}>Active schedules</div>
            <div style={activeSchedulesViewportStyle(activeScheduleCount)}>
              <EnabledSchedulersList
                config={config}
                nextRuns={nextRuns}
                state={state}
                canEdit={false}
                jobRunning={false}
                showActions={false}
              />
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 10 }}>
            <div style={cimSectionLabelStyle}>Schedule type</div>
            <ScheduleTypeTabs
              active={activeScheduleType}
              disabled={saving}
              onSelect={setActiveScheduleType}
            />
          </div>

          <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 10 }}>
            <ScheduleToggle
              enabled={selectedEnabled}
              disabled={saving}
              onChange={setSelectedEnabled}
              label={selectedTitle}
              detail={selectedDetail}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', minWidth: 72 }}>Time (IST)</span>
              <div style={{ flex: 1 }}>
                <IstTimeInput value={selectedTime} disabled={saving || !selectedEnabled} onChange={setSelectedTime} />
              </div>
            </div>
            <div style={{ marginTop: 10, opacity: showingDaily ? 0.42 : 1 }}>
              <div style={cimSectionLabelStyle}>
                Weekday(s): {formatWeekdaysSummary(weeklyWeekdays)}
              </div>
              <WeekdayChips
                weekdays={weeklyWeekdays}
                disabled={saving || showingDaily || !weeklyEnabled}
                onToggle={(idx) => setWeeklyWeekdays((prev) => toggleWeekday(prev, idx))}
              />
            </div>
            <div style={{ marginTop: 10, opacity: selectedEnabled ? 1 : 0.55 }}>
              <DataSourcePicker
                options={options}
                selectedKeys={selectedKeys}
                onToggle={(key) => setSelectedKeys((prev) => toggleInList(prev, key))}
                disabled={saving || !selectedEnabled}
              />
              <TimeframePicker
                label={showingDaily ? 'Daily timeframes' : 'Weekly timeframes'}
                timeframes={timeframeOptions}
                selected={selectedTimeframes}
                onToggle={(tf) => setSelectedTimeframes((prev) => toggleInList(prev, tf))}
                disabled={saving || !selectedEnabled}
              />
            </div>
          </div>

          {message ? (
            <div style={{ fontSize: 11, color: 'var(--accent-green)' }}>{message}</div>
          ) : null}
        </>
      )}
    </CimFormDialog>
  );
}
