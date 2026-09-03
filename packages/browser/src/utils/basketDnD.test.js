import {
  normalizeBasketKind,
  normalizeBasketSymbol,
  readBasketSymbolDrag,
} from './basketDnD';

describe('basketDnD', () => {
  it('normalizes symbol and kind', () => {
    expect(normalizeBasketSymbol('  reliance ')).toBe('RELIANCE');
    expect(normalizeBasketKind('index')).toBe('index');
    expect(normalizeBasketKind('foo')).toBe('stock');
  });

  it('reads MIME payload from drop event', () => {
    const payload = JSON.stringify({ symbol: 'nifty', kind: 'index' });
    const e = {
      dataTransfer: {
        getData: (type) => (type === 'application/x-cim-basket-symbol' ? payload : ''),
      },
    };
    expect(readBasketSymbolDrag(e)).toEqual({ symbol: 'NIFTY', kind: 'index' });
  });
});
