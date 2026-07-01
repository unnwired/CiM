import React from 'react';
import IstTimeInput from './IstTimeInput';
import {
  disabledFieldOpacity,
  fieldLabelStyle,
  fieldSelectStyle,
  FIELD_HEIGHT,
} from './schedulerFieldStyles';
import {
  OHLCV_INTERVALS,
  SCHEDULER_TASKS,
  WEEKDAY_LABELS,
  filterPresetSummary,
  isFilterRebuildTask,
  taskMeta,
  toggleWeekday,
} from './schedulerTasks';

/** Fixed height for interval/time + weekday rows — prevents modal resize on tab switch. */
const SCHEDULE_SECTION_HEIGHT = FIELD_HEIGHT + 10 + FIELD_HEIGHT;

const btnBase = {
  border: 'none',
  borderRadius: 5,
  padding: '8px 14px',
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
};

function ScheduleTypeTabs({ types, active, disabled, onSelect }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
      {types.map((st) => (
        <button
          key={st}
          type="button"
          disabled={disabled}
          aria-pressed={active === st}
          onClick={() => onSelect(st)}
          style={{
            ...btnBase,
            flex: 1,
            minWidth: 0,
            height: FIELD_HEIGHT,
            padding: '0 10px',
            boxSizing: 'border-box',
            backgroundColor: active === st ? 'var(--accent-blue)' : 'var(--bg-primary)',
            color: active === st ? '#fff' : 'var(--text-secondary)',
            border: '1px solid var(--border)',
            cursor: disabled ? 'not-allowed' : 'pointer',
            textTransform: 'capitalize',
          }}
        >
          {st === 'interval' ? 'Interval' : st === 'daily' ? 'Daily' : 'Weekly'}
        </button>
      ))}
    </div>
  );
}

function WeekdayChips({ weekdaysIst, disabled, onToggle }) {
  const selected = new Set(weekdaysIst || [4]);
  return (
    <div style={{
      display: 'flex',
      gap: 4,
      flexWrap: 'nowrap',
      height: FIELD_HEIGHT,
      alignItems: 'center',
      overflowX: 'auto',
      overflowY: 'hidden',
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
          title={selected.has(idx) && selected.size === 1 ? 'At least one weekday required' : `Toggle ${label}`}
          style={{
            ...btnBase,
            height: FIELD_HEIGHT,
            padding: '0 10px',
            fontSize: 11,
            flexShrink: 0,
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

export default function SchedulerTaskEditor({
  selectedKey,
  onSelectKey,
  draft,
  onPatch,
  canEdit,
  jobRunning,
  onEnable,
  onRunNow,
}) {
  const task = taskMeta(selectedKey);
  const f = draft[selectedKey] || {};
  const disabled = !canEdit;
  const scheduleType = f.scheduleType || task.scheduleTypes[0] || 'daily';
  const hasInterval = task.scheduleTypes.includes('interval');
  const hasTimedSchedule = task.scheduleTypes.includes('daily') || task.scheduleTypes.includes('weekly');

  const intervalActive = hasInterval && scheduleType === 'interval';
  const timeActive = hasTimedSchedule && (scheduleType === 'daily' || scheduleType === 'weekly');
  const weekdayActive = scheduleType === 'weekly';
  const filterTask = isFilterRebuildTask(selectedKey);

  function patchTime(t) {
    const [h, m] = t.split(':');
    onPatch(selectedKey, {
      afterTime: t,
      afterHourIst: parseInt(h, 10),
      afterMinuteIst: parseInt(m, 10),
    });
  }

  return (
    <div style={{
      backgroundColor: 'var(--bg-tertiary)',
      borderRadius: 6,
      padding: '10px 12px',
      border: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      flexShrink: 0,
    }}
    >
      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Add / edit schedule
      </div>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
        <span style={{ color: 'var(--text-secondary)' }}>Task</span>
        <select
          value={selectedKey}
          disabled={disabled}
          onChange={(e) => onSelectKey(e.target.value)}
          style={{
            ...fieldSelectStyle,
            width: '100%',
            minWidth: 0,
          }}
        >
          {SCHEDULER_TASKS.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
      </label>
      <div style={{
        fontSize: 11,
        color: 'var(--text-muted)',
        lineHeight: 1.35,
        height: 30,
        overflow: 'hidden',
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
      }}
      >
        {task.desc}
      </div>

      {filterTask && (
        <div style={{
          fontSize: 10,
          color: 'var(--text-secondary)',
          lineHeight: 1.35,
          border: '1px solid var(--border-light)',
          borderRadius: 5,
          padding: '6px 8px',
          backgroundColor: 'var(--bg-primary)',
        }}
        >
          Preset: {filterPresetSummary(f.preset)}
          <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>
            Edit sources and timeframes from Schedule filter data.
          </div>
        </div>
      )}

      <ScheduleTypeTabs
        types={task.scheduleTypes}
        active={scheduleType}
        disabled={disabled}
        onSelect={(st) => onPatch(selectedKey, { scheduleType: st })}
      />

      {/* Fixed-height schedule block — layout never collapses or grows on tab switch */}
      <div style={{
        height: hasTimedSchedule ? SCHEDULE_SECTION_HEIGHT : FIELD_HEIGHT,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        justifyContent: 'flex-start',
      }}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          flexWrap: 'nowrap',
          height: FIELD_HEIGHT,
          flexShrink: 0,
          overflow: 'hidden',
        }}
        >
          {hasInterval ? (
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              color: 'var(--text-secondary)',
              opacity: disabledFieldOpacity(disabled || !intervalActive),
              flexShrink: 0,
            }}
            >
              <span style={fieldLabelStyle}>Every</span>
              <select
                value={f.intervalMinutes ?? 30}
                disabled={disabled || !intervalActive}
                onChange={(e) => onPatch(selectedKey, { intervalMinutes: Number(e.target.value) })}
                style={fieldSelectStyle}
                aria-label="Interval minutes"
              >
                {OHLCV_INTERVALS.map((n) => (
                  <option key={n} value={n}>{n} min</option>
                ))}
              </select>
            </label>
          ) : (
            <span style={{ ...fieldLabelStyle, flexShrink: 0, visibility: 'hidden' }} aria-hidden>Every</span>
          )}

          {hasTimedSchedule && (
            <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
              <IstTimeInput
                value={f.afterTime || task.defaultTime || '15:30'}
                disabled={disabled || !timeActive}
                onChange={patchTime}
              />
            </div>
          )}
        </div>

        {hasTimedSchedule && (
          <WeekdayChips
            weekdaysIst={f.weekdaysIst ?? [task.defaultWeekday ?? 4]}
            disabled={disabled || !weekdayActive}
            onToggle={(idx) => onPatch(selectedKey, { weekdaysIst: toggleWeekday(f.weekdaysIst, idx) })}
          />
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'nowrap', flexShrink: 0 }}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onEnable(selectedKey)}
          style={{ ...btnBase, backgroundColor: '#238636', color: '#fff', opacity: disabled ? 0.5 : 1 }}
        >
          Enable
        </button>
        {!filterTask && (
          <button
            type="button"
            disabled={disabled || jobRunning}
            onClick={() => onRunNow(selectedKey)}
            style={{ ...btnBase, backgroundColor: '#6e40c9', color: '#fff', opacity: jobRunning ? 0.5 : 1 }}
          >
            Run now
          </button>
        )}
      </div>
    </div>
  );
}
