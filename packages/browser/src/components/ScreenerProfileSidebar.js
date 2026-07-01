import React from 'react';
import { EARNINGS_QUARTERLY_PROFILE_WIDTH_PX } from '../config/earningsTableLayout';

const sectionTitleStyle = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 4,
  marginTop: 10,
};

const bodyStyle = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  lineHeight: 1.45,
  margin: 0,
};

function BulletList({ items, color }) {
  if (!items?.length) {
    return <p style={{ ...bodyStyle, color: 'var(--text-muted)', fontStyle: 'italic' }}>—</p>;
  }
  return (
    <ul style={{ margin: 0, paddingLeft: 16, listStyle: 'disc' }}>
      {items.map((item, i) => (
        <li
          key={`${i}-${item.slice(0, 24)}`}
          style={{ ...bodyStyle, color: color || 'var(--text-secondary)', marginBottom: 4 }}
        >
          {item}
        </li>
      ))}
    </ul>
  );
}

export default function ScreenerProfileSidebar({ data, maxHeight, widthPx = EARNINGS_QUARTERLY_PROFILE_WIDTH_PX }) {
  const about = (data?.about || '').trim();
  const keyPoints = (data?.key_points || '').trim();
  const pros = Array.isArray(data?.pros) ? data.pros : [];
  const cons = Array.isArray(data?.cons) ? data.cons : [];
  const hasContent = about || keyPoints || pros.length || cons.length;

  return (
    <aside
      style={{
        flex: `0 0 ${widthPx}px`,
        width: widthPx,
        minWidth: widthPx,
        maxHeight,
        overflowY: 'auto',
        overflowX: 'hidden',
        border: '1px solid var(--border-light)',
        borderRadius: 6,
        backgroundColor: 'var(--bg-secondary)',
        padding: '8px 10px 10px',
        boxSizing: 'border-box',
      }}
      onClick={e => e.stopPropagation()}
    >
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
        Company profile
      </div>
      {!hasContent && (
        <p style={{ ...bodyStyle, color: 'var(--text-muted)' }}>
          Profile not loaded yet. Click <strong style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Refresh</strong> above to fetch company info from Screener.
        </p>
      )}
      {about && (
        <section>
          <div style={{ ...sectionTitleStyle, marginTop: 0 }}>About</div>
          <p style={bodyStyle}>{about}</p>
        </section>
      )}
      {keyPoints && (
        <section>
          <div style={sectionTitleStyle}>Key points</div>
          <p style={bodyStyle}>{keyPoints}</p>
        </section>
      )}
      {(pros.length > 0 || cons.length > 0) && (
        <section>
          <div style={sectionTitleStyle}>Pros &amp; cons</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent-green)', marginBottom: 4 }}>Pros</div>
              <BulletList items={pros} color="var(--text-secondary)" />
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent-red)', marginBottom: 4 }}>Cons</div>
              <BulletList items={cons} color="var(--text-secondary)" />
            </div>
          </div>
          <p style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 8, marginBottom: 0 }}>
            Machine-generated checklist on Screener.in
          </p>
        </section>
      )}
    </aside>
  );
}
