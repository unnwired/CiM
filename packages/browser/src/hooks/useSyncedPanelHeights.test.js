import {
  snapDraggedColumnOnEdgeRelease,
  edgeDividerY,
  PANEL_HEIGHT_DIVIDER_SNAP_THRESHOLD,
} from './useSyncedPanelHeights';

describe('snapDraggedColumnOnEdgeRelease', () => {
  const containerH = 600;
  const panelKeys = ['stochrsi', 'macd'];
  const left = { stochrsi: 130, macd: 130 };
  const right = { stochrsi: 180, macd: 160 };

  it('does not snap when the dragged edge is far from neighbors', () => {
    const dragged = { stochrsi: 200, macd: 200 };
    expect(snapDraggedColumnOnEdgeRelease(
      dragged, 1, 3, left, right, 'price',
      { containerHeight: containerH, panelKeys },
    )).toEqual(dragged);
  });

  it('does not snap the stoch-macd edge when only the price-stoch edge matches', () => {
    const neighbor = { stochrsi: 130, macd: 130 };
    const dragged = { stochrsi: 100, macd: 160 };
    expect(edgeDividerY('price', dragged, containerH, panelKeys))
      .toBe(edgeDividerY('price', neighbor, containerH, panelKeys));
    const stochMacdDragged = edgeDividerY('stochrsi', dragged, containerH, panelKeys);
    const stochMacdNeighbor = edgeDividerY('stochrsi', neighbor, containerH, panelKeys);
    expect(Math.abs(stochMacdDragged - stochMacdNeighbor)).toBeGreaterThan(PANEL_HEIGHT_DIVIDER_SNAP_THRESHOLD);
    expect(snapDraggedColumnOnEdgeRelease(
      dragged, 0, 2, null, neighbor, 'stochrsi',
      { containerHeight: containerH, panelKeys },
    )).toEqual(dragged);
  });

  it('snaps on release when the dragged edge is within threshold', () => {
    const neighbor = { stochrsi: 130, macd: 130 };
    const dragged = { stochrsi: 136, macd: 130 };
    expect(snapDraggedColumnOnEdgeRelease(
      dragged, 0, 2, null, neighbor, 'stochrsi',
      { containerHeight: containerH, panelKeys },
    )).toEqual(neighbor);
  });

  it('snaps first column toward right neighbor only', () => {
    const dragged = { stochrsi: 175, macd: 165 };
    expect(snapDraggedColumnOnEdgeRelease(
      dragged, 0, 3, null, right, 'price',
      { containerHeight: containerH, panelKeys },
    )).toEqual(right);
  });
});
