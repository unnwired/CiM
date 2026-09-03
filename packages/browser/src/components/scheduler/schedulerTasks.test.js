import {
  buildConfigFromForm,
  filterScheduleFromEntry,
  filterScheduleSummary,
  filterScheduleToConfig,
  formFromConfig,
  formatWeekdaysSummary,
  normalizeSnapshotTimeframe,
  normalizeWeekdaysIst,
  scheduleSummary,
  selectSingleWeekday,
  toggleWeekday,
} from './schedulerTasks';

describe('normalizeSnapshotTimeframe', () => {
  it('preserves 30m and uppercases other TFs', () => {
    expect(normalizeSnapshotTimeframe('30m')).toBe('30m');
    expect(normalizeSnapshotTimeframe('30M')).toBe('30m');
    expect(normalizeSnapshotTimeframe('4h')).toBe('4H');
    expect(normalizeSnapshotTimeframe('1d')).toBe('1D');
  });
});

describe('scheduler weekly weekdays', () => {
  it('normalizes and toggles multiple weekdays', () => {
    expect(normalizeWeekdaysIst([0, 2, 2, 6])).toEqual([0, 2, 6]);
    expect(toggleWeekday([0, 2], 4)).toEqual([0, 2, 4]);
    expect(toggleWeekday([0, 2, 4], 2)).toEqual([0, 4]);
    // Last day may be cleared (filter weekly requires ≥1 day before Enable).
    expect(toggleWeekday([0], 0)).toEqual([]);
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
    const cfg = buildConfigFromForm(form, [], [{
      id: 't1',
      taskKey: 'fetchFinancials',
      enabled: true,
      scheduleType: 'weekly',
      weekdaysIst: [0, 2, 4, 6],
      afterHourIst: 2,
      afterMinuteIst: 0,
    }]);
    expect(cfg.fetchFinancials.enabled).toBe(false);
    expect(cfg.taskSchedules).toHaveLength(1);
    expect(cfg.taskSchedules[0].weekdaysIst).toEqual([0, 2, 4, 6]);
    expect(cfg.taskSchedules[0].weekdayIst).toBe(0);
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

describe('filter rebuild scheduleType', () => {
  it('round-trips daily and weekly through filter config helpers', () => {
    const daily = filterScheduleToConfig({
      ...filterScheduleFromEntry({
        id: 'd1',
        scheduleType: 'daily',
        afterHourIst: 23,
        afterMinuteIst: 0,
        weekdaysIst: [],
        preset: { keys: ['ema'], timeframes: ['1D'] },
      }),
      scheduleType: 'daily',
    });
    expect(daily.scheduleType).toBe('daily');
    expect(daily.weekdaysIst).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(filterScheduleSummary(daily)).toContain('Daily');

    const weekly = filterScheduleToConfig(filterScheduleFromEntry({
      id: 'w1',
      scheduleType: 'weekly',
      afterHourIst: 2,
      afterMinuteIst: 0,
      weekdaysIst: [0, 2],
      preset: { keys: ['macd'], timeframes: ['1W'] },
    }));
    expect(weekly.scheduleType).toBe('weekly');
    expect(weekly.weekdaysIst).toEqual([0, 2]);
    expect(filterScheduleSummary(weekly)).toContain('Mon, Wed');
  });

  it('round-trips monthly single weekday for filter rebuild', () => {
    const monthly = filterScheduleToConfig({
      id: 'm1',
      scheduleType: 'monthly',
      afterHourIst: 23,
      afterMinuteIst: 0,
      weekdaysIst: [0, 2, 4],
      preset: { keys: ['ema'], timeframes: ['1D'] },
    });
    expect(monthly.scheduleType).toBe('monthly');
    expect(monthly.weekdaysIst).toEqual([0]);
    expect(filterScheduleSummary(monthly)).toContain('First Mon of month');
  });

  it('preserves 30m when saving filter rebuild schedule', () => {
    const saved = filterScheduleToConfig(filterScheduleFromEntry({
      id: 'tf30',
      scheduleType: 'weekly',
      afterHourIst: 23,
      afterMinuteIst: 0,
      weekdaysIst: [0],
      preset: { keys: ['macd'], timeframes: ['30m', '4H', '1D'] },
    }));
    expect(saved.preset.timeframes).toEqual(['30m', '4H', '1D']);
  });

  it('selectSingleWeekday is exclusive', () => {
    expect(selectSingleWeekday([2], 0)).toEqual([0]);
    expect(selectSingleWeekday([0], 0)).toEqual([]);
  });
});
