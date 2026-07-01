import {
  buildConfigFromForm,
  formFromConfig,
  formatWeekdaysSummary,
  normalizeWeekdaysIst,
  scheduleSummary,
  toggleWeekday,
} from './schedulerTasks';

describe('scheduler weekly weekdays', () => {
  it('normalizes and toggles multiple weekdays', () => {
    expect(normalizeWeekdaysIst([0, 2, 2, 6])).toEqual([0, 2, 6]);
    expect(toggleWeekday([0, 2], 4)).toEqual([0, 2, 4]);
    expect(toggleWeekday([0, 2, 4], 2)).toEqual([0, 4]);
    expect(toggleWeekday([0], 0)).toEqual([0]);
  });

  it('round-trips weekdaysIst through form config', () => {
    const form = formFromConfig({
      fetchFinancials: {
        enabled: true,
        scheduleType: 'weekly',
        weekdaysIst: [0, 2, 4, 6],
        afterHourIst: 2,
        afterMinuteIst: 0,
      },
    });
    expect(form.fetchFinancials.weekdaysIst).toEqual([0, 2, 4, 6]);
    const cfg = buildConfigFromForm(form);
    expect(cfg.fetchFinancials.weekdaysIst).toEqual([0, 2, 4, 6]);
    expect(cfg.fetchFinancials.weekdayIst).toBe(0);
  });

  it('migrates legacy weekdayIst to weekdaysIst', () => {
    const form = formFromConfig({
      fetchFinancials: { enabled: true, scheduleType: 'weekly', weekdayIst: 5 },
    });
    expect(form.fetchFinancials.weekdaysIst).toEqual([5]);
  });

  it('formats multi-day schedule summary', () => {
    expect(formatWeekdaysSummary([0, 2, 4])).toBe('Mon, Wed, Fri');
    expect(scheduleSummary('fetchFinancials', {
      enabled: true,
      scheduleType: 'weekly',
      weekdaysIst: [0, 2, 4],
      afterHourIst: 2,
      afterMinuteIst: 0,
    })).toBe('Mon, Wed, Fri 02:00 IST');
  });
});
