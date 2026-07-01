import React, { useEffect, useMemo, useRef, useState } from 'react';
import { buildMarketMapTreemapLayout } from '../utils/marketMapTreemapLayout';
import {
  EARNINGS_PLUS_COLOR,
  MM_TEXT_PRIMARY,
  MM_TEXT_SECONDARY,
  tileBackground,
  tilePctColor,
} from '../utils/marketMapTileStyle';

function formatPct(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  const n = Number(v);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

export default function MarketMapTreemap({ constituents, onOpenChart, groupBySector = true }) {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(entries => {
      const cr = entries[0]?.contentRect;
      if (cr) setSize({ w: Math.floor(cr.width), h: Math.floor(cr.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layout = useMemo(
    () => buildMarketMapTreemapLayout(constituents, size.w, size.h, { groupBySector }),
    [constituents, size.w, size.h, groupBySector],
  );

  const { nodes, hasCapData } = layout;

  if (size.w < 40 || size.h < 40) {
    return <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 280 }} />;
  }

  if (!constituents.length) {
    return (
      <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 280 }}>
        <div style={{ padding: 8, color: 'var(--text-muted)', fontSize: 12 }}>No constituent data.</div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 280,
        backgroundColor: 'var(--bg-primary)',
      }}
    >
      {!hasCapData && (
        <div style={{
          position: 'absolute',
          top: 6,
          left: 8,
          right: 8,
          zIndex: 2,
          fontSize: 10,
          color: 'var(--text-muted)',
          pointerEvents: 'none',
        }}
        >
          Limited market-cap data — tile sizes are approximate. Run Update to refresh screener.
        </div>
      )}
      {[...nodes].sort((a, b) => (a.isLeaf === b.isLeaf ? 0 : a.isLeaf ? 1 : -1)).map(node => {
        if (node.isSector) {
          if (node.w < 48 || node.h < 24) return null;
          return (
            <div
              key={node.id}
              style={{
                position: 'absolute',
                left: node.x0,
                top: node.y0,
                width: node.w,
                height: node.h,
                boxSizing: 'border-box',
                border: '1px solid var(--border)',
                borderRadius: 4,
                backgroundColor: 'rgba(22, 27, 34, 0.85)',
                pointerEvents: 'none',
                overflow: 'hidden',
              }}
            >
              <span style={{
                position: 'absolute',
                top: 4,
                left: 6,
                fontSize: 10,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: node.w - 12,
              }}
              >
                {node.sector}
              </span>
            </div>
          );
        }

        const stock = node.stock;
        if (!stock || node.w < 6 || node.h < 6) return null;

        const pct = stock.change_pct;
        const bg = tileBackground(pct);
        const pctColor = tilePctColor(pct, bg);
        const showSymbol = node.w >= 36 && node.h >= 22;
        const showPct = node.w >= 44 && node.h >= 28;
        const showName = node.w >= 72 && node.h >= 40;
        const earningsPlus = !!stock.earnings_plus;

        return (
          <button
            key={node.id}
            type="button"
            title={`${stock.symbol} ${formatPct(pct)}${earningsPlus ? ' · Earnings+' : ''}`}
            onClick={() => onOpenChart && onOpenChart(stock.symbol)}
            style={{
              position: 'absolute',
              left: node.x0,
              top: node.y0,
              width: node.w,
              height: node.h,
              boxSizing: 'border-box',
              margin: 0,
              padding: showName ? '6px 8px' : '4px 6px',
              border: earningsPlus
                ? `2px solid ${EARNINGS_PLUS_COLOR}`
                : '1px solid rgba(0,0,0,0.25)',
              borderRadius: 2,
              backgroundColor: bg,
              cursor: 'pointer',
              zIndex: 1,
              textAlign: 'left',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}
          >
            {showSymbol && (
              <span style={{
                fontSize: node.w >= 80 ? 11 : 10,
                fontWeight: 700,
                color: MM_TEXT_PRIMARY,
                lineHeight: 1.15,
                maxWidth: '100%',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              >
                {stock.symbol}
              </span>
            )}
            {showName && (
              <span style={{
                fontSize: 9,
                color: MM_TEXT_SECONDARY,
                maxWidth: '100%',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              >
                {stock.company_name}
              </span>
            )}
            {showPct && (
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 600,
                color: pctColor,
                marginTop: 'auto',
              }}
              >
                {formatPct(pct)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
