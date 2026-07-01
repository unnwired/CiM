import {
  hydrateListOrderFields,
  LIST_ORDER_KEYS,
  loadLocalListOrders,
  saveLocalListOrders,
  buildListOrderPayload,
  hasStarTagsContent,
} from './listOrderPersistence';

describe('listOrderPersistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('prefers server equity index order when server is newer', () => {
    saveLocalListOrders('user@test.com', {
      equityIndexSymbolOrder: ['OLD'],
      layoutOrdersSavedAt: '2026-01-01T00:00:00.000Z',
    });
    const { orders, usedLocal } = hydrateListOrderFields({
      equityIndexSymbolOrder: ['NEW'],
      layoutOrdersSavedAt: '2026-06-01T00:00:00.000Z',
    }, 'user@test.com');
    expect(orders.equityIndexSymbolOrder).toEqual(['NEW']);
    expect(usedLocal).toBe(false);
  });

  it('falls back to local when server field is missing', () => {
    saveLocalListOrders(null, {
      portfolioRowOrder: ['stock:RELIANCE'],
      layoutOrdersSavedAt: '2026-06-01T00:00:00.000Z',
    });
    const { orders, usedLocal } = hydrateListOrderFields({}, null);
    expect(orders.portfolioRowOrder).toEqual(['stock:RELIANCE']);
    expect(usedLocal).toBe(true);
  });

  it('migrates legacy indicesEquitySymbolOrder from server', () => {
    const { orders } = hydrateListOrderFields({
      indicesEquitySymbolOrder: ['NIFTY', 'BANKNIFTY'],
    }, null);
    expect(orders.equityIndexSymbolOrder).toEqual(['NIFTY', 'BANKNIFTY']);
  });

  it('buildListOrderPayload stamps savedAt', () => {
    const { payload } = buildListOrderPayload({
      [LIST_ORDER_KEYS.watchlistItemOrder]: { Main: ['stock:TCS'] },
    });
    expect(payload.watchlistItemOrder).toEqual({ Main: ['stock:TCS'] });
    expect(payload.layoutOrdersSavedAt).toBeTruthy();
  });

  it('hydrates indexStarTags from server', () => {
    const { orders } = hydrateListOrderFields({
      indexStarTags: { 'NIFTY 50': 'golden', 'NIFTY BANK': 'blue' },
    }, null);
    expect(orders.indexStarTags).toEqual({ 'NIFTY 50': 'golden', 'NIFTY BANK': 'blue' });
  });

  it('buildListOrderPayload includes indexStarTags', () => {
    const { payload } = buildListOrderPayload({
      [LIST_ORDER_KEYS.indexStarTags]: { 'NIFTY 50': 'green' },
    });
    expect(payload.indexStarTags).toEqual({ 'NIFTY 50': 'green' });
  });

  it('prefers server star tags over empty local object', () => {
    saveLocalListOrders('user@test.com', {
      indexStarTags: {},
      layoutOrdersSavedAt: '2026-06-01T00:00:00.000Z',
    });
    const { orders } = hydrateListOrderFields({
      indexStarTags: { 'NIFTY 50': 'golden' },
      layoutOrdersSavedAt: '2026-01-01T00:00:00.000Z',
    }, 'user@test.com');
    expect(orders.indexStarTags).toEqual({ 'NIFTY 50': 'golden' });
  });

  it('restores star tags from chart prefs backup when server missing', () => {
    const { orders, needsStarTagsServerSync } = hydrateListOrderFields(
      {},
      'user@test.com',
      { indexStarTags: { 'NIFTY BANK': 'blue' } },
    );
    expect(orders.indexStarTags).toEqual({ 'NIFTY BANK': 'blue' });
    expect(needsStarTagsServerSync).toBe(true);
    expect(hasStarTagsContent(orders.indexStarTags)).toBe(true);
  });

  it('buildListOrderPayload can persist cleared star tags', () => {
    const { payload } = buildListOrderPayload({
      [LIST_ORDER_KEYS.indexStarTags]: {},
    });
    expect(payload.indexStarTags).toEqual({});
  });
});
