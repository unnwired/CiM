import React from 'react';
import {
  fmtIst,
  isFilterRebuildTask,
  lastRunLine,
  scheduleSummary,
  SCHEDULER_TASKS,
} from './schedulerTasks';

const btnSm = {
  border: 'none',
  borderRadius: 4,
  padding: '4px 10px',
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
};

export default function EnabledSchedulersList({
  config = {},
  nextRuns = {},
  state = {},
  canEdit,
  jobRunning,
  onRemove,
  onRunNow,
  showActions = true,
}) {
  const enabled = SCHEDULER_TASKS
    .filter((t) => config[t.key]?.enabled)
    .sort((a, b) => {
      const an = nextRuns[a.key] ? new Date(nextRuns[a.key]).getTime() : Number.MAX_SAFE_INTEGER;
      const bn = nextRuns[b.key] ? new Date(nextRuns[b.key]).getTime() : Number.MAX_SAFE_INTEGER;
      return an - bn;
    });

  if (!enabled.length) {
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
        Choose a task below, set when it should run, then click Enable.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {enabled.map((task) => {
        const c = config[task.key] || {};
        const scheduleOnly = isFilterRebuildTask(task.key);
        return (
          <div
            key={task.key}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr auto',
              gap: 8,
              alignItems: 'center',
              padding: '6px 8px',
              borderRadius: 6,
              border: '1px solid var(--border)',
              backgroundColor: 'var(--bg-tertiary)',
            }}
          >
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{task.label}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                {scheduleSummary(task.key, c)}
                {' · Next '}
                {fmtIst(nextRuns[task.key])}
                {' · '}
                {lastRunLine(task.key, state)}
              </div>
            </div>
            {showActions && (
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {!scheduleOnly && (
                  <button
                    type="button"
                    disabled={!canEdit || jobRunning}
                    onClick={() => onRunNow(task.key)}
                    style={{ ...btnSm, backgroundColor: '#238636', color: '#fff', opacity: jobRunning ? 0.5 : 1 }}
                  >
                    Run now
                  </button>
                )}
                <button
                  type="button"
                  disabled={!canEdit}
                  onClick={() => onRemove(task.key)}
                  style={{ ...btnSm, backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  Remove
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
