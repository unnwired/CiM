/** Shared control sizing for Admin Scheduler — one height/weight for all fields. */

export const FIELD_HEIGHT = 32;
export const FIELD_FONT = 13;
export const FIELD_RADIUS = 4;
export const FIELD_BORDER = '1px solid var(--border)';

export const fieldInputStyle = {
  width: 56,
  height: FIELD_HEIGHT,
  padding: '0 8px',
  fontSize: FIELD_FONT,
  borderRadius: FIELD_RADIUS,
  border: FIELD_BORDER,
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  textAlign: 'center',
  boxSizing: 'border-box',
};

export const fieldSelectStyle = {
  minWidth: 72,
  height: FIELD_HEIGHT,
  padding: '0 8px',
  fontSize: FIELD_FONT,
  borderRadius: FIELD_RADIUS,
  border: FIELD_BORDER,
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  boxSizing: 'border-box',
};

export const fieldLabelStyle = {
  fontSize: 11,
  color: 'var(--text-muted)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
};

export function disabledFieldOpacity(isDisabled) {
  return isDisabled ? 0.42 : 1;
}

/** Active schedules list — row slot for scroll cap; grows with content up to four rows. */
export const ACTIVE_SCHEDULE_ROW_SLOT_PX = 50;
export const ACTIVE_SCHEDULES_MAX_VISIBLE = 4;
export const ACTIVE_SCHEDULES_SCROLL_MAX_HEIGHT = ACTIVE_SCHEDULE_ROW_SLOT_PX * ACTIVE_SCHEDULES_MAX_VISIBLE;

/** @param {number} activeCount — enabled tasks in the active list */
export function activeSchedulesViewportStyle(activeCount) {
  if (activeCount > ACTIVE_SCHEDULES_MAX_VISIBLE) {
    return {
      maxHeight: ACTIVE_SCHEDULES_SCROLL_MAX_HEIGHT,
      overflowY: 'auto',
    };
  }
  return { overflowY: 'visible' };
}
