import { screenerFinancialsUrl } from './externalFinancialsLinks';

describe('screenerFinancialsUrl', () => {
  test('consolidated points at /consolidated/#quarters', () => {
    expect(screenerFinancialsUrl('DEEPAKNTR', 'consolidated')).toBe(
      'https://www.screener.in/company/DEEPAKNTR/consolidated/#quarters',
    );
  });

  test('standalone points at /#quarters', () => {
    expect(screenerFinancialsUrl('DEEPAKNTR', 'standalone')).toBe(
      'https://www.screener.in/company/DEEPAKNTR/#quarters',
    );
  });

  test('defaults to consolidated when basis omitted', () => {
    expect(screenerFinancialsUrl('DEEPAKNTR')).toBe(
      'https://www.screener.in/company/DEEPAKNTR/consolidated/#quarters',
    );
  });

  test('treats unknown basis as standalone', () => {
    expect(screenerFinancialsUrl('DEEPAKNTR', 'weird')).toBe(
      'https://www.screener.in/company/DEEPAKNTR/#quarters',
    );
  });
});
