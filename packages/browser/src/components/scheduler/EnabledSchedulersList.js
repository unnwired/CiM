import React, { useEffect, useRef, useState } from 'react';
import {
  FILTER_REBUILD_TASK_META,
  filterLastRunLine,
  filterScheduleSummary,
  fmtIst,
  scheduleSummary,
  SCHEDULER_TASKS,
  taskLastRunLine,
  taskMeta,
} from './schedulerTasks';

const btnSm = {
  border: 'none',
  borderRadius: 4,
  padding: '4px 10px',
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
};

function ScheduleActionsMenu({
  canEdit,
  jobRunning,
  enabled,
  onEnable,
  onDisable,
  onDelete,
  onRunNow,
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onDoc(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const items = [
    enabled
      ? { key: 'disable', label: 'Disable', onClick: onDisable, danger: false }
      : { key: 'enable', label: 'Enable', onClick: onEnable, danger: false },
    {
      key: 'run',
      label: 'Run now',
      onClick: onRunNow,
      disabled: !enabled,
    },
    { key: 'delete', label: 'Delete', onClick: onDelete, danger: true },
  ];

  return (
    <div ref={rootRef} style={{ position: 'relative', flexShrink: 0 }}>
      <button
        type="button"
        disabled={!canEdit}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        style={{
          ...btnSm,
          backgroundColor: 'var(--bg-primary)',
          color: 'var(--text-secondary)',
          border: '1px solid var(--border)',
          opacity: !canEdit ? 0.5 : 1,
          minWidth: 64,
        }}
      >
        Actions ▾
      </button>
      {open && (
        <div
          role="menu"
          style={{
            position: 'absolute',
            right: 0,
            top: '100%',
            marginTop: 4,
            zIndex: 20,
            minWidth: 120,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
            padding: 4,
          }}
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              disabled={!!item.disabled || !canEdit}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                if (!item.disabled) item.onClick?.();
              }}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                border: 'none',
                background: 'transparent',
                borderRadius: 4,
                padding: '7px 10px',
                fontSize: 12,
                fontWeight: 600,
                color: item.danger ? 'var(--accent-red)' : 'var(--text-primary)',
                cursor: item.disabled || !canEdit ? 'not-allowed' : 'pointer',
                opacity: item.disabled || !canEdit ? 0.45 : 1,
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusDot({ enabled }) {
  return (
    <span
      aria-hidden="true"
      title={enabled ? 'Enabled' : 'Disabled'}
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        flexShrink: 0,
        backgroundColor: enabled ? '#3fb950' : '#f85149',
        boxShadow: enabled
          ? '0 0 0 2px rgba(63,185,80,0.25)'
          : '0 0 0 2px rgba(248,81,73,0.25)',
      }}
    />
  );
}

export default function EnabledSchedulersList({
  config = {},
  taskSchedules = [],
  filterSchedules = [],
  filterOptions = null,
  nextRuns = {},
  state = {},
  canEdit,
  jobRunning,
  onEnableTask,
  onDisableTask,
  onDeleteTask,
  onEnableFilter,
  onDisableFilter,
  onDeleteFilter,
  onRunNow,
  onEdit,
  selectedKey = null,
}) {
  const taskRows = (taskSchedules || []).map((entry) => ({
    kind: 'task',
    key: `task:${entry.id}`,
    entry,
  }));

  // Only schedules that were explicitly created (persisted). Disabled filters
  // stay visible so the operator can Enable them again from Actions.
  const filterRows = (filterSchedules || []).map((entry) => ({
    kind: 'filter',
    key: `filter:${entry.id}`,
    entry,
  }));

  const rows = [...taskRows, ...filterRows].sort((a, b) => {
    const an = nextRuns[a.key] ? new Date(nextRuns[a.key]).getTime() : Number.MAX_SAFE_INTEGER;
    const bn = nextRuns[b.key] ? new Date(nextRuns[b.key]).getTime() : Number.MAX_SAFE_INTEGER;
    return an - bn;
  });

  if (!rows.length) {
    return (
      <div style={{
        padding: '8px 10px',
        borderRadius: 6,
        border: '1px dashed var(--border)',
        color: 'var(--text-muted)',
        fontSize: 11,
        lineHeight: 1.4,
      }}
      >
        <strong style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>No active schedules.</strong>
        {' '}
        Configure a task below, then click Create Schedule. You can add the same task multiple times at different times.
      </div>
    );
  }

  const byKey = new Map((filterOptions?.items || []).map((it) => [it.key, it.label]));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {rows.map((row) => {
        if (row.kind === 'filter') {
          const entry = row.entry;
          const isSelected = selectedKey === row.key;
          const sourceNames = (entry.preset?.keys || []).map((k) => byKey.get(k) || k);
          return (
            <div
              key={row.key}
              onClick={onEdit ? () => onEdit(row.key) : undefined}
              title={onEdit ? 'Click to edit this schedule' : undefined}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                gap: 8,
                alignItems: 'center',
                padding: '6px 8px',
                borderRadius: 6,
                border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
                backgroundColor: isSelected ? 'rgba(56,139,253,0.08)' : 'var(--bg-tertiary)',
                cursor: onEdit ? 'pointer' : 'default',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                }}
                >
                  <StatusDot enabled={!!entry.enabled} />
                  <span>{FILTER_REBUILD_TASK_META.label}</span>
                  <span style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: entry.enabled ? '#3fb950' : '#f85149',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                  >
                    {entry.enabled ? 'On' : 'Off'}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                  {filterScheduleSummary(entry, filterOptions)}
                  {' · Next '}
                  {fmtIst(nextRuns[row.key])}
                  {' · '}
                  {filterLastRunLine(entry.id, state)}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2, wordBreak: 'break-word' }}>
                  {sourceNames.length ? sourceNames.join(', ') : 'No data sources selected'}
                </div>
              </div>
              <ScheduleActionsMenu
                canEdit={canEdit}
                jobRunning={jobRunning}
                enabled={!!entry.enabled}
                onEnable={() => onEnableFilter?.(entry.id)}
                onDisable={() => onDisableFilter?.(entry.id)}
                onDelete={() => onDeleteFilter?.(entry.id)}
                onRunNow={() => onRunNow?.(row.key)}
              />
            </div>
          );
        }

        const entry = row.entry;
        const meta = taskMeta(entry.taskKey) || SCHEDULER_TASKS[0];
        const isSelected = selectedKey === row.key;
        return (
          <div
            key={row.key}
            onClick={onEdit ? () => onEdit(row.key) : undefined}
            title={onEdit ? 'Click to edit this schedule' : undefined}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr auto',
              gap: 8,
              alignItems: 'center',
              padding: '6px 8px',
              borderRadius: 6,
              border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border)'}`,
              backgroundColor: isSelected ? 'rgba(56,139,253,0.08)' : 'var(--bg-tertiary)',
              cursor: onEdit ? 'pointer' : 'default',
            }}
          >
            <div>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}
              >
                <StatusDot enabled={!!entry.enabled} />
                <span>{meta.label}</span>
                <span style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: entry.enabled ? '#3fb950' : '#f85149',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
                >
                  {entry.enabled ? 'On' : 'Off'}
                </span>
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                {scheduleSummary(entry.taskKey, { ...entry, enabled: true })}
                {' · Next '}
                {fmtIst(nextRuns[row.key])}
                {' · '}
                {taskLastRunLine(entry.id, state)}
              </div>
            </div>
            <ScheduleActionsMenu
              canEdit={canEdit}
              jobRunning={jobRunning}
              enabled={!!entry.enabled}
              onEnable={() => onEnableTask?.(entry.id)}
              onDisable={() => onDisableTask?.(entry.id)}
              onDelete={() => onDeleteTask?.(entry.id)}
              onRunNow={() => onRunNow?.(row.key)}
            />
          </div>
        );
      })}
    </div>
  );
}
