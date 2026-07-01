/** NSE / TradingView symbol -> Screener.in /company/{slug}/ path segment */

const SCREENER_COMPANY_SLUG_ALIASES = {
  BAJAJ_AUTO: 'BAJAJ-AUTO',
  BAJAJAUTO: 'BAJAJ-AUTO',
  M_M: 'M&M',
};

export function screenerCompanySlugCandidates(symbol) {
  const sym = String(symbol || '').trim().toUpperCase();
  if (!sym) return [];

  const out = [];
  const add = (slug) => {
    if (slug && !out.includes(slug)) out.push(slug);
  };

  const alias = SCREENER_COMPANY_SLUG_ALIASES[sym];
  if (alias) add(alias);

  if (sym.endsWith('AUTO') && sym.length > 4 && !sym.includes('-') && !sym.includes('_')) {
    add(`${sym.slice(0, -4)}-AUTO`);
  }

  if (sym.includes('_')) add(sym.replace(/_/g, '-'));

  add(sym);
  return out;
}

export function screenerCompanySlug(symbol) {
  const candidates = screenerCompanySlugCandidates(symbol);
  return candidates[0] || '';
}
