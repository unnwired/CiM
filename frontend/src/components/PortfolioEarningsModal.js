import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { EarningsQuarterlyPanelContent } from './EarningsQuarterlyPanel';
import ExternalFinancialsLinks from './ExternalFinancialsLinks';
import { formatEarningsBadgeDate } from '../utils/portfolioEarnings';
import {
  PORTFOLIO_EARNINGS_MODAL_PROFILE_WIDTH_PX,
  PORTFOLIO_EARNINGS_MODAL_WIDTH_PX,
} from '../config/earningsTableLayout';

export default function PortfolioEarningsModal({
  symbol,
  variant = 'upcoming',
  earningsDate,
  daysUntil,
  daysSinceReport,
  comparisonStatus = 'verified',
  comparisonNote = '',
  onClose,
  onOpenChart,
}) {
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previouslyFocusedRef = useRef(null);

  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement;
    window.setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 0);
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key !== 'Tab') return;
      const root = dialogRef.current;
      if (!root) return;
      const focusables = root.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      previouslyFocusedRef.current?.focus?.();
    };
  }, [onClose]);

  const dateLabel = formatEarningsBadgeDate(earningsDate) || earningsDate;
  const isBeat = variant === 'beat';
  const isReportedMiss = variant === 'reported_miss';
  const daysLabel = daysUntil === 0
    ? 'today'
    : daysUntil === 1
      ? 'in 1 day'
      : `in ${daysUntil} days`;
  const reportedAgoLabel = daysSinceReport === 0
    ? 'today'
    : daysSinceReport === 1
      ? '1 day ago'
      : `${daysSinceReport} days ago`;
  const subtitle = isBeat
    ? `Beat EPS+Rev · reported ${dateLabel} · ${reportedAgoLabel}`
    : isReportedMiss
      ? `Reported ${dateLabel} · ${reportedAgoLabel} · Missed EPS or revenue`
      : `Upcoming earnings ${dateLabel} · ${daysLabel}`;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="portfolio-earnings-modal-title"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.62)',
        zIndex: 18000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        style={{
          width: `min(${PORTFOLIO_EARNINGS_MODAL_WIDTH_PX}px, 98vw)`,
          maxHeight: 'min(90vh, 920px)',
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          boxShadow: '0 20px 48px rgba(0,0,0,0.6)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            flexShrink: 0,
            backgroundColor: 'var(--bg-tertiary)',
          }}
        >
          <div id="portfolio-earnings-modal-title" style={{ minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
              {symbol}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {subtitle}
            </div>
            {comparisonStatus !== 'verified' && comparisonNote ? (
              <div style={{ fontSize: 10, color: '#d29922', marginTop: 4 }}>
                {comparisonNote}
              </div>
            ) : null}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close earnings details"
            style={{ background: 'none', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1, flexShrink: 0 }}
          >
            ×
          </button>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
          <EarningsQuarterlyPanelContent
            symbol={symbol}
            profileWidthPx={PORTFOLIO_EARNINGS_MODAL_PROFILE_WIDTH_PX}
            scrollTableToLatest
          />
        </div>
        <div
          style={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 14px',
            borderTop: '1px solid var(--border)',
            backgroundColor: 'var(--bg-secondary)',
            minHeight: 46,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: 13,
              color: 'var(--text-primary)',
              flexShrink: 0,
            }}
          >
            {symbol}
          </span>
          <div style={{ width: 1, height: 22, backgroundColor: 'var(--border)', flexShrink: 0 }} />
          <ExternalFinancialsLinks
            symbol={symbol}
            height={28}
            layout="inline"
            includeTvEarnings
            onOpenChart={onOpenChart || null}
            screenerLabel="Screener ↗"
            tradingViewLabel="TV Overview ↗"
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
