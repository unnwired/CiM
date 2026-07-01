import { scheduleResizeDelta } from './PanelResizeHandle';

describe('scheduleResizeDelta', () => {
  let rafCb;

  beforeEach(() => {
    rafCb = null;
    jest.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      rafCb = cb;
      return 42;
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('accumulates deltas and flushes once per animation frame', () => {
    const pending = { current: 0 };
    const raf = { current: null };
    const onResize = jest.fn();

    scheduleResizeDelta(pending, raf, 3, onResize);
    scheduleResizeDelta(pending, raf, 5, onResize);
    expect(onResize).not.toHaveBeenCalled();
    expect(raf.current).toBe(42);

    rafCb();
    expect(onResize).toHaveBeenCalledTimes(1);
    expect(onResize).toHaveBeenCalledWith(8);
    expect(raf.current).toBeNull();
    expect(pending.current).toBe(0);
  });

  it('schedules a new frame after the previous flush', () => {
    const pending = { current: 0 };
    const raf = { current: null };
    const onResize = jest.fn();

    scheduleResizeDelta(pending, raf, 4, onResize);
    rafCb();
    scheduleResizeDelta(pending, raf, 2, onResize);
    rafCb();

    expect(onResize).toHaveBeenNthCalledWith(1, 4);
    expect(onResize).toHaveBeenNthCalledWith(2, 2);
  });
});
