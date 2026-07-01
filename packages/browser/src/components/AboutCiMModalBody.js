import React from 'react';

const sectionHeadingStyle = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 8,
  marginTop: 0,
};

const paragraphStyle = {
  fontSize: 12,
  lineHeight: 1.55,
  color: 'var(--text-secondary)',
  margin: '0 0 10px',
};

const sectionStyle = {
  marginBottom: 16,
};

const footerStyle = {
  fontSize: 11,
  lineHeight: 1.5,
  color: 'var(--text-muted)',
  margin: 0,
  paddingTop: 4,
  borderTop: '1px solid var(--border)',
};

export default function AboutCiMModalBody() {
  return (
    <div style={{ textAlign: 'left', width: '100%' }}>
      <section style={sectionStyle}>
        <h3 style={sectionHeadingStyle}>What Charts In Motion is</h3>
        <p style={{ ...paragraphStyle, marginBottom: 0 }}>
          Charts In Motion is an offline-first charting and research workspace for Indian equities. It is a
          solo-built, independent project designed to help you explore price action, screen the
          market, and review context in one place — without jumping between many websites and tools.
        </p>
      </section>

      <section style={sectionStyle}>
        <h3 style={sectionHeadingStyle}>A work in progress</h3>
        <p style={{ ...paragraphStyle, marginBottom: 0 }}>
          Charts In Motion is far from complete. A great deal remains to be built, refined, and polished — treat
          it as an evolving workspace, not a finished product. Development is shaped by input from
          people who use it: report issues and feature requests from the cog menu, and capabilities
          are prioritised and shipped in updates based on that feedback.
        </p>
      </section>

      <section style={sectionStyle}>
        <h3 style={sectionHeadingStyle}>How the data works</h3>
        <p style={paragraphStyle}>
          Charts and tables are built from stored exchange data, primarily NSE-listed symbols. Some
          fundamentals and classifications may draw on BSE-sourced or third-party reference data
          where noted in the app.
        </p>
        <p style={{ ...paragraphStyle, marginBottom: 0 }}>
          Updates are not live by default. Quotes, OHLC, and most tables refresh when you run a
          refresh or when background data jobs have been run on your machine. The only section with
          optional live polling today is Market Movers (when Live refresh is enabled). Even then,
          prices can be delayed, incomplete, or stale — especially outside market hours or after a
          failed refresh.
        </p>
      </section>

      <section style={sectionStyle}>
        <h3 style={sectionHeadingStyle}>What Charts In Motion is for</h3>
        <p style={{ ...paragraphStyle, marginBottom: 0 }}>
          Charts In Motion is designed to help you see structure in the market: trends, breadth, sector
          behaviour, earnings context, and your own watchlists and holdings. It is meant to reduce
          friction so you can form your own view — your one workspace for exploration.
        </p>
      </section>

      <section style={sectionStyle}>
        <h3 style={sectionHeadingStyle}>What Charts In Motion is not</h3>
        <p style={paragraphStyle}>
          Charts In Motion is not investment advice, a recommendation service, or a signal that a stock will
          rise or fall. Nothing in the app certifies future performance. Do not trade or invest
          based solely on what you see here. Always cross-check with official exchange and company
          sources and your own judgment.
        </p>
      </section>

      <section style={{ ...sectionStyle, marginBottom: 12 }}>
        <h3 style={sectionHeadingStyle}>Your responsibility</h3>
        <p style={{ ...paragraphStyle, marginBottom: 0 }}>
          You are responsible for how you use this tool. Charts In Motion helps you understand market depth and
          context; it does not replace due diligence, professional advice, or your risk management.
        </p>
      </section>

      <p style={footerStyle}>
        Version and data timestamps are shown where available. When in doubt, refresh data or check
        Data Management.
      </p>
    </div>
  );
}
