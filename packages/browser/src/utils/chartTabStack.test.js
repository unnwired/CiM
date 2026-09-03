import {
  activateChartInStack,
  activeChart,
  closeActiveChartInStack,
  closeChartInStack,
  findChartInStacks,
  openChartInStacks,
  setActiveChartSymbol,
} from './chartTabStack';

describe('chartTabStack', () => {
  test('open first chart creates a stack', () => {
    const r = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'DEEPAKNTR',
      originView: 'dashboard',
      maxStacks: 5,
      now: 1000,
    });
    expect(r.stacks).toHaveLength(1);
    expect(activeChart(r.stacks[0]).symbol).toBe('DEEPAKNTR');
    expect(r.activeStackIdx).toBe(0);
    expect(r.creationOrder).toEqual(['stack-1000']);
  });

  test('open while viewing a chart stacks under the same slot', () => {
    const first = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'DEEPAKNTR',
      originView: 'dashboard',
      maxStacks: 5,
      now: 1000,
    });
    const r = openChartInStacks({
      stacks: first.stacks,
      creationOrder: first.creationOrder,
      activeStackIdx: first.activeStackIdx,
      viewIsChart: true,
      symbol: 'UNOMINDA',
      originView: null,
      maxStacks: 5,
      now: 2000,
    });
    expect(r.stacks).toHaveLength(1);
    expect(r.stacks[0].charts.map((c) => c.symbol)).toEqual(['DEEPAKNTR', 'UNOMINDA']);
    expect(r.stacks[0].activeIdx).toBe(1);
    expect(activeChart(r.stacks[0]).symbol).toBe('UNOMINDA');
  });

  test('open from non-chart view still stacks under the existing slot', () => {
    const first = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'DEEPAKNTR',
      originView: 'dashboard',
      maxStacks: 5,
      now: 1000,
    });
    const r = openChartInStacks({
      stacks: first.stacks,
      creationOrder: first.creationOrder,
      activeStackIdx: first.activeStackIdx,
      viewIsChart: false,
      symbol: 'RELIANCE',
      originView: 'watchlist',
      maxStacks: 5,
      now: 2000,
    });
    expect(r.stacks).toHaveLength(1);
    expect(r.stacks[0].charts.map((c) => c.symbol)).toEqual(['DEEPAKNTR', 'RELIANCE']);
    expect(activeChart(r.stacks[0]).symbol).toBe('RELIANCE');
  });

  test('reopening an existing symbol focuses it in its stack', () => {
    let state = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'DEEPAKNTR',
      originView: null,
      maxStacks: 5,
      now: 1000,
    });
    state = openChartInStacks({
      ...state,
      viewIsChart: true,
      symbol: 'UNOMINDA',
      originView: null,
      maxStacks: 5,
      now: 2000,
    });
    const found = findChartInStacks(state.stacks, 'DEEPAKNTR');
    expect(found).toEqual({ stackIdx: 0, chartIdx: 0 });
    const r = openChartInStacks({
      ...state,
      viewIsChart: true,
      symbol: 'DEEPAKNTR',
      originView: null,
      maxStacks: 5,
      now: 3000,
    });
    expect(r.stacks).toHaveLength(1);
    expect(r.stacks[0].activeIdx).toBe(0);
  });

  test('close active chart leaves the rest of the stack', () => {
    let state = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'A',
      originView: 'dashboard',
      maxStacks: 5,
      now: 1,
    });
    state = openChartInStacks({
      ...state,
      viewIsChart: true,
      symbol: 'B',
      originView: null,
      maxStacks: 5,
      now: 2,
    });
    const closed = closeActiveChartInStack(state.stacks, state.creationOrder, 0);
    expect(closed.removedStack).toBe(false);
    expect(closed.stacks[0].charts.map((c) => c.symbol)).toEqual(['A']);
    expect(activeChart(closed.stacks[0]).symbol).toBe('A');
  });

  test('close last chart removes the stack', () => {
    const state = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'A',
      originView: 'dashboard',
      maxStacks: 5,
      now: 1,
    });
    const closed = closeActiveChartInStack(state.stacks, state.creationOrder, 0);
    expect(closed.removedStack).toBe(true);
    expect(closed.stacks).toHaveLength(0);
    expect(closed.closedReturnView).toBe('dashboard');
    expect(closed.creationOrder).toEqual([]);
  });

  test('close non-active chart from list keeps active selection', () => {
    let state = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'A',
      originView: null,
      maxStacks: 5,
      now: 1,
    });
    state = openChartInStacks({
      ...state,
      viewIsChart: true,
      symbol: 'B',
      originView: null,
      maxStacks: 5,
      now: 2,
    });
    state = openChartInStacks({
      ...state,
      viewIsChart: true,
      symbol: 'C',
      originView: null,
      maxStacks: 5,
      now: 3,
    });
    // active is C (idx 2); close A (idx 0)
    const closed = closeChartInStack(state.stacks, state.creationOrder, 0, 0);
    expect(closed.stacks[0].charts.map((c) => c.symbol)).toEqual(['B', 'C']);
    expect(closed.stacks[0].activeIdx).toBe(1);
    expect(activeChart(closed.stacks[0]).symbol).toBe('C');
  });

  test('activateChartInStack and setActiveChartSymbol', () => {
    let stacks = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'A',
      originView: null,
      maxStacks: 5,
      now: 1,
    }).stacks;
    stacks = openChartInStacks({
      stacks,
      creationOrder: ['stack-1'],
      activeStackIdx: 0,
      viewIsChart: true,
      symbol: 'B',
      originView: null,
      maxStacks: 5,
      now: 2,
    }).stacks;
    stacks = activateChartInStack(stacks, 0, 0);
    expect(activeChart(stacks[0]).symbol).toBe('A');
    stacks = setActiveChartSymbol(stacks, 0, 'AAA');
    expect(activeChart(stacks[0]).symbol).toBe('AAA');
  });

  test('entryMeta preserves name for constituents-style stacking', () => {
    const first = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'NIFTY',
      originView: 'indices',
      maxStacks: 5,
      now: 1000,
      entryMeta: { name: 'Nifty 50' },
    });
    expect(activeChart(first.stacks[0]).name).toBe('Nifty 50');
    const r = openChartInStacks({
      stacks: first.stacks,
      creationOrder: first.creationOrder,
      activeStackIdx: first.activeStackIdx,
      viewIsChart: false,
      symbol: 'BANKNIFTY',
      originView: null,
      maxStacks: 5,
      now: 2000,
      entryMeta: { name: 'Nifty Bank' },
    });
    expect(r.stacks).toHaveLength(1);
    expect(r.stacks[0].charts.map((c) => c.symbol)).toEqual(['NIFTY', 'BANKNIFTY']);
    expect(r.stacks[0].charts.map((c) => c.name)).toEqual(['Nifty 50', 'Nifty Bank']);
    expect(activeChart(r.stacks[0]).symbol).toBe('BANKNIFTY');
  });

  test('reopening constituents index focuses and refreshes name', () => {
    let state = openChartInStacks({
      stacks: [],
      creationOrder: [],
      activeStackIdx: null,
      viewIsChart: false,
      symbol: 'NIFTY',
      originView: null,
      maxStacks: 5,
      now: 1,
      entryMeta: { name: 'Nifty 50' },
    });
    state = openChartInStacks({
      ...state,
      viewIsChart: false,
      symbol: 'BANKNIFTY',
      originView: null,
      maxStacks: 5,
      now: 2,
      entryMeta: { name: 'Nifty Bank' },
    });
    const r = openChartInStacks({
      ...state,
      viewIsChart: false,
      symbol: 'NIFTY',
      originView: null,
      maxStacks: 5,
      now: 3,
      entryMeta: { name: 'NIFTY 50' },
    });
    expect(r.stacks).toHaveLength(1);
    expect(r.stacks[0].activeIdx).toBe(0);
    expect(activeChart(r.stacks[0]).name).toBe('NIFTY 50');
  });
});
