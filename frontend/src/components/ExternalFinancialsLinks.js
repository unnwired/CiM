import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  screenerFinancialsUrl,
  tradingViewFinancialsUrl,
  tradingViewEarningsUrl,
} from '../utils/externalFinancialsLinks';
import { openExternalUrl } from '../utils/openExternalUrl';

const MENU_Z = 10050;

const baseLinkStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  padding: '0 10px',
  color: 'var(--text-secondary)',
  fontSize: 12,
  flexShrink: 0,
  textDecoration: 'none',
};

const baseBtnStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  padding: '0 10px 0 12px',
  color: 'var(--text-secondary)',
  fontSize: 12,
  fontWeight: 600,
  flexShrink: 0,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  fontFamily: 'inherit',
};

const chartBtnStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  padding: '0 10px',
  color: 'var(--text-secondary)',
  fontSize: 12,
  flexShrink: 0,
  cursor: 'pointer',
  fontFamily: 'inherit',
};

function linkHoverHandlers() {
  return {
    onMouseEnter: e => {
      e.currentTarget.style.borderColor = 'var(--accent-blue)';
      e.currentTarget.style.color = 'var(--accent-blue)';
    },
    onMouseLeave: e => {
      e.currentTarget.style.borderColor = 'var(--border)';
      e.currentTarget.style.color = 'var(--text-secondary)';
    },
  };
}

/**
 * Screener.in + TradingView financials (NSE stocks). Hidden for indices.
 * layout="dropdown" (default): Financials menu → Screener, TradingView, …
 * layout="inline": separate horizontal buttons (e.g. earnings tab footer).
 */
export default function ExternalFinancialsLinks({
  symbol,
  instrumentType = 'stock',
  height = 28,
  layout = 'dropdown',
  includeTvEarnings = false,
  onOpenChart = null,
  screenerLabel = 'Screener ↗',
  tradingViewLabel = 'TradingView ↗',
  tvEarningsLabel = 'TV Earnings ↗',
}) {
  const sym = String(symbol || '').trim().toUpperCase();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuRect, setMenuRect] = useState(null);
  const anchorRef = useRef(null);

  const screenerHref = screenerFinancialsUrl(sym);
  const tvHref = tradingViewFinancialsUrl(sym);
  const tvEarningsHref = includeTvEarnings ? tradingViewEarningsUrl(sym) : null;
  const hasChart = typeof onOpenChart === 'function';
  const hasFinancialsLinks = screenerHref || tvHref || tvEarningsHref;
  const useDropdown = layout === 'dropdown';

  useLayoutEffect(() => {
    if (!useDropdown || !menuOpen) {
      setMenuRect(null);
      return;
    }
    const update = () => {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const width = 200;
      const pad = 8;
      const left = Math.min(Math.max(pad, r.left), Math.max(pad, window.innerWidth - width - pad));
      setMenuRect({ top: r.bottom + 4, left, width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [menuOpen, useDropdown]);

  useEffect(() => {
    if (!useDropdown || !menuOpen) return;
    const onDoc = e => {
      if (anchorRef.current?.contains(e.target)) return;
      setMenuOpen(false);
    };
    const onKey = e => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen, useDropdown]);

  if (!sym || instrumentType === 'index') return null;
  if (!hasFinancialsLinks && !hasChart) return null;

  const btnHeight = height;
  const hover = linkHoverHandlers();
  const linkStyle = { ...baseLinkStyle, height: btnHeight };

  const menuItems = [];
  if (screenerHref) {
    menuItems.push({
      key: 'screener',
      label: screenerLabel,
      href: screenerHref,
      title: `Screener.in financials — ${sym}`,
      tvStyle: false,
    });
  }
  if (tvHref) {
    menuItems.push({
      key: 'tv',
      label: tradingViewLabel,
      href: tvHref,
      title: `TradingView overview — NSE:${sym}`,
      tvStyle: true,
    });
  }
  if (tvEarningsHref) {
    menuItems.push({
      key: 'tv-earnings',
      label: tvEarningsLabel,
      href: tvEarningsHref,
      title: `TradingView earnings (FQ) — NSE:${sym}`,
      tvStyle: false,
    });
  }

  return (
    <span
      className="chart-toolbar-external-links"
      data-flowx="external-financials"
      style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}
    >
      {hasChart && (
        <button
          type="button"
          title={`Open chart — ${sym}`}
          style={{ ...chartBtnStyle, height: btnHeight }}
          onClick={() => onOpenChart(sym)}
          {...hover}
        >
          Chart
        </button>
      )}
      {useDropdown && hasFinancialsLinks && (
        <div ref={anchorRef} style={{ position: 'relative', flexShrink: 0 }}>
          <button
            type="button"
            title={`Financials — ${sym}`}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            onClick={() => setMenuOpen(o => !o)}
            style={{
              ...baseBtnStyle,
              height: btnHeight,
              backgroundColor: menuOpen ? 'var(--bg-active)' : 'var(--bg-tertiary)',
            }}
          >
            <span>Financials</span>
            <svg width="10" height="6" viewBox="0 0 10 6" fill="currentColor" style={{ opacity: 0.65, flexShrink: 0 }}>
              <path d="M0 0l5 6 5-6z" />
            </svg>
          </button>
          {menuOpen && menuRect && (
            <div
              role="menu"
              style={{
                position: 'fixed',
                top: menuRect.top,
                left: menuRect.left,
                width: menuRect.width,
                zIndex: MENU_Z,
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
                overflow: 'hidden',
              }}
            >
              {menuItems.map(item => (
                <a
                  key={item.key}
                  role="menuitem"
                  href={item.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={item.title}
                  onClick={e => {
                    openExternalUrl(item.href, e);
                    setMenuOpen(false);
                  }}
                  style={{
                    display: 'block',
                    padding: '9px 14px',
                    fontSize: 12,
                    color: 'var(--text-secondary)',
                    textDecoration: 'none',
                    fontWeight: item.tvStyle ? 600 : 400,
                    borderBottom: '1px solid var(--border-light)',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                >
                  {item.label}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
      {!useDropdown && screenerHref && (
        <a
          href={screenerHref}
          target="_blank"
          rel="noopener noreferrer"
          title={`Screener.in financials — ${sym}`}
          style={linkStyle}
          onClick={e => openExternalUrl(screenerHref, e)}
          {...hover}
        >
          {screenerLabel}
        </a>
      )}
      {!useDropdown && tvHref && (
        <a
          href={tvHref}
          target="_blank"
          rel="noopener noreferrer"
          title={`TradingView overview — NSE:${sym}`}
          style={{
            ...linkStyle,
            fontWeight: 600,
            borderColor: 'rgba(41, 98, 255, 0.45)',
          }}
          onClick={e => openExternalUrl(tvHref, e)}
          {...hover}
        >
          {tradingViewLabel}
        </a>
      )}
      {!useDropdown && tvEarningsHref && (
        <a
          href={tvEarningsHref}
          target="_blank"
          rel="noopener noreferrer"
          title={`TradingView earnings (FQ) — NSE:${sym}`}
          style={linkStyle}
          onClick={e => openExternalUrl(tvEarningsHref, e)}
          {...hover}
        >
          {tvEarningsLabel}
        </a>
      )}
    </span>
  );
}
