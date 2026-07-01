import {
  ACTIVE_SCHEDULES_MAX_VISIBLE,
  ACTIVE_SCHEDULES_SCROLL_MAX_HEIGHT,
  activeSchedulesViewportStyle,
} from './schedulerFieldStyles';

describe('activeSchedulesViewportStyle', () => {
  it('does not reserve height when empty or up to max visible', () => {
    for (let count = 0; count <= ACTIVE_SCHEDULES_MAX_VISIBLE; count += 1) {
      expect(activeSchedulesViewportStyle(count)).toEqual({ overflowY: 'visible' });
    }
  });

  it('caps height and scrolls beyond max visible rows', () => {
    expect(activeSchedulesViewportStyle(5)).toEqual({
      maxHeight: ACTIVE_SCHEDULES_SCROLL_MAX_HEIGHT,
      overflowY: 'auto',
    });
    expect(activeSchedulesViewportStyle(10)).toEqual({
      maxHeight: ACTIVE_SCHEDULES_SCROLL_MAX_HEIGHT,
      overflowY: 'auto',
    });
  });
});
