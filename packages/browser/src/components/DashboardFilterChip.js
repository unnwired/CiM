import React from 'react';

/** Filter pill on the NSE dashboard bar — label, enable/disable toggle, inline remove, optional drag handle. */
export default function DashboardFilterChip({
  filter,
  onEdit,
  onToggle,
  onRemove,
  draggable = false,
  dimmed = false,
  onDragHandleStart,
  onDragHandleEnd,
}) {
  const enabled = filter?.enabled !== false;
  const borderColor = enabled ? 'var(--accent-blue)' : 'var(--border)';
  const labelColor = enabled ? 'var(--accent-blue)' : 'var(--text-secondary)';

  return (
    <div
      className="dashboard-filter-chip"
      style={{ opacity: dimmed ? 0.45 : 1 }}
    >
      {draggable ? (
        <span
          className="dashboard-filter-chip-drag"
          title="Drag to reorder"
          draggable
          onDragStart={(e) => {
            e.stopPropagation();
            onDragHandleStart?.(e);
          }}
          onDragEnd={(e) => {
            e.stopPropagation();
            onDragHandleEnd?.(e);
          }}
          onClick={(e) => e.stopPropagation()}
        >
          ⋮⋮
        </span>
      ) : null}
      <div
        className={`dashboard-filter-chip-body${enabled ? '' : ' dashboard-filter-chip-body--disabled'}`}
        style={{ border: `1px solid ${borderColor}` }}
      >
        <span
          className="dashboard-filter-chip-label"
          onClick={onEdit}
          title={filter.label}
          style={{ color: labelColor }}
        >
          {filter.label}
        </span>
        <button
          type="button"
          className="dashboard-filter-chip-toggle"
          onClick={onToggle}
          title={enabled ? 'Disable filter' : 'Enable filter'}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              backgroundColor: enabled ? 'var(--accent-blue)' : 'var(--text-muted)',
              opacity: enabled ? 1 : 0.65,
            }}
          />
        </button>
        <span className="dashboard-filter-chip-divider" aria-hidden="true" />
        <button
          type="button"
          className="dashboard-filter-chip-remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          title="Remove filter"
          aria-label="Remove filter"
        >
          <svg width="6" height="6" viewBox="0 0 10 10" fill="none" aria-hidden="true">
            <path d="M2 2L8 8M8 2L2 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
