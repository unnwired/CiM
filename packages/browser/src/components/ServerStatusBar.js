import React from 'react';

const HEALTH_DOT_LABELS = {
  green: 'Server healthy',
  amber: 'Server degraded',
  red: 'Server unreachable',
  loading: 'Checking server status',
  unknown: 'Checking server status',
};

function resolveHealthDotState(healthState) {
  if (healthState === 'loading' || healthState === 'unknown') return 'loading';
  if (HEALTH_DOT_LABELS[healthState]) return healthState;
  return 'red';
}

export default function ServerStatusBar({
  healthState = 'loading',
  usersOnline = null,
  inline = false,
}) {
  const countLabel = (typeof usersOnline === 'number' && Number.isFinite(usersOnline))
    ? String(usersOnline)
    : '—';
  const dotState = resolveHealthDotState(healthState);
  const dotLabel = HEALTH_DOT_LABELS[dotState] || HEALTH_DOT_LABELS.red;

  const panel = (
    <div className="cim-server-status-panel">
        <div className="cim-server-status-line">
          <span className="cim-server-status-label">Server Status:</span>
          <span
            className={`cim-health-dot cim-health-dot--${dotState}`}
            role="img"
            aria-label={dotLabel}
            title={dotLabel}
          />
        </div>
        <div className="cim-server-status-line">
          <span className="cim-server-status-label">Users Online:</span>
          <strong className="cim-users-online-count">{countLabel}</strong>
        </div>
    </div>
  );

  if (inline) {
    return (
      <div className="cim-server-status-cell" aria-live="polite">
        <div className="cim-server-status-inline">{panel}</div>
      </div>
    );
  }

  return (
    <div className="cim-server-status-bar" aria-live="polite">
      {panel}
    </div>
  );
}
