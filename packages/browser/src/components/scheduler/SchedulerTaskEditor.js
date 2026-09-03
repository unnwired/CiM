import React, { useEffect, useState } from 'react';
import axios from 'axios';
import IstTimeInput from './IstTimeInput';
import {
  disabledFieldOpacity,
  fieldSelectStyle,
  FIELD_HEIGHT,
} from './schedulerFieldStyles';
import {
  EDITOR_TASK_OPTIONS,
  FILTER_FULL_TIMEFRAMES,
  FILTER_REBUILD_KEY,
  isFilterRebuildKey,
  isTaskScheduleKey,
  selectSingleWeekday,
  taskMeta,
  toggleWeekday,
  WEEKDAY_LABELS,
} from './schedulerTasks';

const API = '';

const ALL_SCHEDULE_TYPES = ['daily', 'weekly', 'monthly'];

const btnBase = {
  border: 'none',
  borderRadius: 5,
  padding: '8px 14px',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

const sectionLabelStyle = {
  fontSize: 11,
  color: 'var(--text-muted)',
  fontWeight: 600,
  marginBottom: 6,
};

/** Fixed skeleton: all three tabs always shown; per-tab + global disabling. */
function ScheduleTypeTabs({ active, enabledTypes, disabled, onSelect }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
      {ALL_SCHEDULE_TYPES.map((st) => {
        const tabEnabled = !disabled && enabledTypes.includes(st);
        const isActive = active === st;
        return (
          <button
            key={st}
            type="button"
            disabled={!tabEnabled}
            aria-pressed={isActive}
            onClick={() => onSelect(st)}
            style={{
              ...btnBase,
              flex: 1,
              minWidth: 0,
              height: FIELD_HEIGHT,
              padding: '0 10px',
              boxSizing: 'border-box',
              backgroundColor: isActive && tabEnabled ? 'var(--accent-blue)' : 'var(--bg-primary)',
              color: isActive && tabEnabled ? '#fff' : 'var(--text-secondary)',
              border: '1px solid var(--border)',
              cursor: tabEnabled ? 'pointer' : 'not-allowed',
              opacity: tabEnabled ? 1 : disabledFieldOpacity(true),
              textTransform: 'capitalize',
            }}
          >
            {st === 'daily' ? 'Daily' : st === 'weekly' ? 'Weekly' : 'Monthly'}
          </button>
        );
      })}
    </div>
  );
}

function WeekdayChips({ weekdaysIst, disabled, onToggle }) {
  const selected = new Set(weekdaysIst || []);
  return (
    <div style={{
      display: 'flex',
      gap: 4,
      flexWrap: 'nowrap',
      height: FIELD_HEIGHT,
      alignItems: 'center',
      opacity: disabledFieldOpacity(disabled),
    }}
    >
      {WEEKDAY_LABELS.map((label, idx) => (
        <button
          key={label}
          type="button"
          disabled={disabled}
          onClick={() => onToggle(idx)}
          aria-pressed={selected.has(idx)}
          title={`Toggle ${label}`}
          style={{
            ...btnBase,
            flex: 1,
            minWidth: 0,
            height: FIELD_HEIGHT,
            padding: '0 6px',
            fontSize: 11,
            boxSizing: 'border-box',
            backgroundColor: selected.has(idx) && !disabled
              ? 'var(--accent-blue)'
              : 'var(--bg-primary)',
            color: selected.has(idx) && !disabled ? '#fff' : 'var(--text-secondary)',
            border: '1px solid var(--border)',
            cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** Small binary toggle switch: Incremental (left/off) ↔ Full (right/on). */
function ModeSwitch({ mode, disabled, onChange }) {
  const isFull = mode === 'full';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, height: FIELD_HEIGHT, opacity: disabledFieldOpacity(disabled) }}>
      <span style={{
        fontSize: 12,
        fontWeight: isFull ? 400 : 600,
        color: isFull ? 'var(--text-muted)' : 'var(--text-primary)',
      }}
      >
        Incremental
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={isFull}
        aria-label="Rebuild mode: Incremental or Full"
        disabled={disabled}
        onClick={() => onChange(isFull ? 'incremental' : 'full')}
        style={{
          position: 'relative',
          width: 40,
          height: 22,
          flexShrink: 0,
          borderRadius: 11,
          border: '1px solid var(--border)',
          backgroundColor: isFull ? 'var(--accent-blue)' : 'var(--bg-primary)',
          cursor: disabled ? 'not-allowed' : 'pointer',
          padding: 0,
          transition: 'background-color 0.15s ease',
        }}
      >
        <span style={{
          position: 'absolute',
          top: 2,
          left: 2,
          width: 16,
          height: 16,
          borderRadius: '50%',
          backgroundColor: '#fff',
          boxShadow: '0 1px 2px rgba(0,0,0,0.4)',
          transform: isFull ? 'translateX(18px)' : 'translateX(0)',
          transition: 'transform 0.15s ease',
        }}
        />
      </button>
      <span style={{
        fontSize: 12,
        fontWeight: isFull ? 600 : 400,
        color: isFull ? 'var(--text-primary)' : 'var(--text-muted)',
      }}
      >
        Full
      </span>
    </div>
  );
}

function toggleInList(list, value) {
  const set = new Set(list);
  if (set.has(value)) set.delete(value);
  else set.add(value);
  return [...set];
}

export default function SchedulerTaskEditor({
  selectedKey,
  onSelectKey,
  taskDraft,
  filterDraft,
  onPatchTask,
  onPatchFilter,
  canEdit,
  isCreateMode = true,
  onCreate,
  onSave,
  onCancel,
}) {
  const filterMode = isFilterRebuildKey(selectedKey);
  const taskKey = filterMode
    ? FILTER_REBUILD_KEY
    : (taskDraft?.taskKey || (isTaskScheduleKey(selectedKey) ? null : selectedKey) || 'ohlcv');
  const task = taskMeta(taskKey);
  const f = filterMode ? (filterDraft || {}) : (taskDraft || {});
  const disabled = !canEdit;
  const scheduleType = filterMode
    ? (f.scheduleType === 'daily' || f.scheduleType === 'monthly' ? f.scheduleType : 'weekly')
    : (f.scheduleType || task.scheduleTypes[0] || 'daily');

  // Which schedule-type tabs this task supports.
  const enabledTypes = task.scheduleTypes;

  // Per-field enable flags (Option A: fields always rendered, disabled when N/A).
  const timeEnabled = !disabled && (scheduleType === 'daily' || scheduleType === 'weekly' || scheduleType === 'monthly');
  const weekdayEnabled = !disabled && (scheduleType === 'weekly' || scheduleType === 'monthly');
  const filterFieldsEnabled = !disabled && filterMode;

  const [filterOptions, setFilterOptions] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/admin/filter-rebuild/options`)
      .then((r) => { if (!cancelled) setFilterOptions(r.data); })
      .catch(() => { if (!cancelled) setFilterOptions(null); });
    return () => { cancelled = true; };
  }, []);

  const allTimeframes = filterOptions?.snapshot_timeframes || FILTER_FULL_TIMEFRAMES;
  const selectedKeys = filterMode ? (f.preset?.keys || []) : [];
  const selectedTimeframes = filterMode ? (f.preset?.timeframes || []) : [];

  const weekdaysValue = f.weekdaysIst ?? (filterMode ? [] : [task.defaultWeekday ?? 4]);

  // Filter rebuild requires sources + timeframes; weekly/monthly also need day(s).
  const noSourcesSelected = filterMode && selectedKeys.length === 0;
  const noWeekdaysSelected = (filterMode || scheduleType === 'weekly' || scheduleType === 'monthly')
    && (scheduleType === 'weekly' || scheduleType === 'monthly')
    && (weekdaysValue?.length ?? 0) === 0;
  const noTimeframesSelected = filterMode && selectedTimeframes.length === 0;
  const blockCreate = noSourcesSelected || noWeekdaysSelected || noTimeframesSelected;

  const missingBits = [];
  if (noWeekdaysSelected) {
    missingBits.push(scheduleType === 'monthly' ? 'one first weekday of month' : 'one day of week');
  }
  if (noSourcesSelected) missingBits.push('one data source');
  if (noTimeframesSelected) missingBits.push('one timeframe');
  const blockWarning = missingBits.length
    ? `Select at least ${missingBits.join(', ')} to create this schedule.`
    : '';

  function patchTime(t) {
    const [h, m] = t.split(':');
    const patch = {
      afterTime: t,
      afterHourIst: parseInt(h, 10),
      afterMinuteIst: parseInt(m, 10),
    };
    if (filterMode) onPatchFilter(patch);
    else onPatchTask(patch);
  }

  function patchFilter(patch) {
    onPatchFilter(patch);
  }

  function selectScheduleType(st) {
    const patch = { scheduleType: st };
    if (st === 'monthly') {
      const days = weekdaysValue || [];
      patch.weekdaysIst = days.length ? [days[0]] : [];
      patch.weekdayIst = patch.weekdaysIst[0] ?? 0;
    }
    if (filterMode) {
      patchFilter(patch);
      return;
    }
    onPatchTask(patch);
  }

  function toggleWeekdayField(idx) {
    const next = scheduleType === 'monthly'
      ? selectSingleWeekday(weekdaysValue, idx)
      : toggleWeekday(weekdaysValue, idx);
    if (filterMode) patchFilter({ weekdaysIst: next, weekdayIst: next[0] });
    else onPatchTask({ weekdaysIst: next, weekdayIst: next[0] });
  }

  function setMode(nextMode) {
    // Only change the mode; never auto-select timeframes (they stay as the
    // operator left them — empty by default).
    patchFilter({
      mode: nextMode,
      preset: {
        ...(f.preset || {}),
        mode: nextMode,
      },
    });
  }

  const primaryLabel = isCreateMode ? 'Create Schedule' : 'Save Changes';
  const primaryAction = isCreateMode ? onCreate : onSave;
  const primaryBlocked = blockCreate;

  const taskSelectValue = filterMode ? FILTER_REBUILD_KEY : (taskDraft?.taskKey || 'ohlcv');

  return (
    <div style={{
      backgroundColor: 'var(--bg-tertiary)',
      borderRadius: 6,
      padding: '10px 12px',
      border: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      flexShrink: 0,
    }}
    >
      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {isCreateMode ? 'Create schedule' : 'Edit schedule'}
      </div>

      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
        <span style={{ color: 'var(--text-secondary)' }}>Task</span>
        <select
          value={taskSelectValue}
          disabled={disabled || !isCreateMode}
          onChange={(e) => {
            const next = e.target.value;
            onSelectKey(next === FILTER_REBUILD_KEY ? FILTER_REBUILD_KEY : next);
          }}
          style={{ ...fieldSelectStyle, width: '100%', minWidth: 0 }}
        >
          {EDITOR_TASK_OPTIONS.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
      </label>

      <div style={{
        fontSize: 11,
        color: 'var(--text-muted)',
        lineHeight: 1.35,
        height: 30,
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}
      >
        {task.desc}
      </div>

      {/* Frequency tabs — always present */}
      <div>
        <div style={sectionLabelStyle}>Frequency</div>
        <ScheduleTypeTabs
          active={scheduleType}
          enabledTypes={enabledTypes}
          disabled={disabled}
          onSelect={selectScheduleType}
        />
      </div>

      {/* Time — IST */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: 16,
        height: FIELD_HEIGHT,
      }}
      >
        <div style={{ flexShrink: 0, opacity: disabledFieldOpacity(!timeEnabled) }}>
          <IstTimeInput
            value={f.afterTime || task.defaultTime || '15:30'}
            disabled={!timeEnabled}
            onChange={patchTime}
          />
        </div>
      </div>

      {/* Days of week / first weekday of month */}
      <div style={{ opacity: disabledFieldOpacity(!weekdayEnabled) }}>
        <div style={sectionLabelStyle}>
          {scheduleType === 'monthly' ? 'First weekday of month' : 'Days of week'}
        </div>
        <WeekdayChips
          weekdaysIst={weekdaysValue}
          disabled={!weekdayEnabled}
          onToggle={toggleWeekdayField}
        />
        {scheduleType === 'monthly' && (
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.35 }}>
            Single choice — runs on the first selected weekday of each month (e.g. first Monday).
          </div>
        )}
      </div>

      {/* Rebuild mode — always present (filter-only) */}
      <div style={{ opacity: disabledFieldOpacity(!filterFieldsEnabled) }}>
        <div style={sectionLabelStyle}>Rebuild mode</div>
        <ModeSwitch
          mode={filterMode ? (f.mode || f.preset?.mode || 'incremental') : 'incremental'}
          disabled={!filterFieldsEnabled}
          onChange={setMode}
        />
      </div>

      {/* Data sources — always present (filter-only) */}
      <div style={{ opacity: disabledFieldOpacity(!filterFieldsEnabled) }}>
        <div style={sectionLabelStyle}>Data sources</div>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          border: '1px solid var(--border)',
          borderRadius: 5,
          padding: '8px 10px',
          backgroundColor: 'var(--bg-primary)',
        }}
        >
          {(filterOptions?.items || []).length === 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Loading data sources…</div>
          )}
          {(filterOptions?.items || []).map((it) => {
            const checked = selectedKeys.includes(it.key);
            return (
              <label key={it.key} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--text-secondary)', cursor: !filterFieldsEnabled ? 'not-allowed' : 'pointer' }}>
                <input
                  type="checkbox"
                  disabled={!filterFieldsEnabled}
                  checked={checked}
                  onChange={() => patchFilter({ preset: { ...(f.preset || {}), keys: toggleInList(selectedKeys, it.key) } })}
                />
                {it.label}
              </label>
            );
          })}
        </div>
      </div>

      {/* Timeframes — always present (filter-only) */}
      <div style={{ opacity: disabledFieldOpacity(!filterFieldsEnabled) }}>
        <div style={sectionLabelStyle}>Timeframes</div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {allTimeframes.map((tf) => {
            const on = selectedTimeframes.includes(tf);
            return (
              <button
                key={tf}
                type="button"
                disabled={!filterFieldsEnabled}
                onClick={() => patchFilter({ preset: { ...(f.preset || {}), timeframes: toggleInList(selectedTimeframes, tf) } })}
                style={{
                  ...btnBase,
                  height: 28,
                  padding: '0 8px',
                  fontSize: 10,
                  backgroundColor: on ? 'var(--accent-blue)' : 'var(--bg-primary)',
                  color: on ? '#fff' : 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                  cursor: !filterFieldsEnabled ? 'not-allowed' : 'pointer',
                }}
              >
                {tf}
              </button>
            );
          })}
        </div>
      </div>

      {/* Fixed-height slot for the validation warning so the panel never reflows */}
      <div style={{ minHeight: 16, fontSize: 11, color: 'var(--accent-red)' }}>
        {blockWarning}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'nowrap', flexShrink: 0 }}>
        <button
          type="button"
          disabled={disabled || primaryBlocked}
          onClick={() => primaryAction?.()}
          style={{ ...btnBase, backgroundColor: '#238636', color: '#fff', opacity: (disabled || primaryBlocked) ? 0.5 : 1 }}
        >
          {primaryLabel}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onCancel?.()}
          style={{
            ...btnBase,
            backgroundColor: 'var(--bg-primary)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border)',
            opacity: disabled ? 0.5 : 1,
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
