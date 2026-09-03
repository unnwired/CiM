"""Charts In Motion Knowledge Base — JSON store under data/knowledge_base.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Order matches the main tab bar in App.js (NSE → Indices → Market Map → …).
KB_PAGE_IDS = (
    "dashboard",
    "indices",
    "funds",
    "market-map",
    "market-pulse",
    "market-movers",
    "earnings-beats",
    "watchlist",
    "portfolio",
    "pnl",
    "potential-swings",
    "index-chart",
    "constituents",
    "chart",
)

KB_PAGE_LABELS: dict[str, str] = {
    "dashboard": "NSE",
    "indices": "Indices",
    "funds": "Funds",
    "market-map": "Market Map",
    "market-pulse": "Market Pulse",
    "market-movers": "Market Movers",
    "earnings-beats": "Earnings",
    "watchlist": "Watchlist",
    "portfolio": "Portfolio",
    "pnl": "P&L",
    "potential-swings": "Potential Swings",
    "index-chart": "Index Chart",
    "constituents": "Index Constituents",
    "chart": "Stock Chart",
}

KB_PAGE_GROUPS: dict[str, str] = {
    "dashboard": "main",
    "indices": "main",
    "funds": "main",
    "market-map": "main",
    "market-pulse": "main",
    "market-movers": "main",
    "earnings-beats": "main",
    "watchlist": "main",
    "portfolio": "main",
    "pnl": "main",
    "potential-swings": "main",
    "index-chart": "opened",
    "constituents": "opened",
    "chart": "opened",
}

PAGE_STUBS: dict[str, dict[str, Any]] = {
    "funds": {
        "title": "Funds",
        "sections": [
            {
                "heading": "What the Funds page is for",
                "paragraphs": [
                    "Funds is Charts In Motion's mutual fund workspace. It brings Indian open-ended mutual fund schemes into the same chart-and-list layout you already use for stocks, so you can study a fund's NAV history with candles, EMAs, and indicators instead of reading a static returns table on a fund house website.",
                    "The layout matches the rest of the app: a searchable fund list on the left, a daily NAV chart on the right, and a draggable divider between them.",
                    "Use it to compare how a fund has actually behaved over months and years — trend, drawdowns, recovery, momentum — rather than judging it only by a headline 1Y or 3Y return number.",
                ],
            },
            {
                "heading": "Where the fund data comes from",
                "paragraphs": [
                    "The scheme catalog and daily NAVs come from AMFI (Association of Mutual Funds in India) — the industry body every Indian AMC reports NAVs to. Charts In Motion downloads AMFI's open-ended NAV file and stores each scheme's code, name, AMC, category, ISIN, and latest NAV.",
                    "NAV history for a fund you open is backfilled on demand (roughly the last 90 days to start) and then grows day by day as each AMFI refresh lands. The longer you run Charts In Motion, the deeper your own NAV history becomes.",
                    "Only open-ended schemes are listed. Close-ended and interval schemes are excluded because they are not continuously purchasable and their NAV series is not comparable.",
                    "NAVs are end-of-day only. There is no intraday or live fund data anywhere in the market — a mutual fund publishes one NAV per business day after markets close — so Funds refreshes only after 15:30 IST. Intraday Update runs for stocks do not touch funds by design.",
                ],
            },
            {
                "heading": "Which schemes are listed (Direct–Growth)",
                "paragraphs": [
                    "By default the list shows Direct–Growth plans only. AMFI publishes several plan variants of the same fund — Regular vs Direct, and Growth vs IDCW (dividend) — which would otherwise flood the list with four or more near-identical rows per scheme.",
                    "Direct plans carry no distributor commission, so their NAV series reflects the fund manager's performance rather than the sales channel. Growth plans reinvest gains instead of paying them out, so the NAV line is continuous and not broken by dividend payouts.",
                    "That combination — Direct plus Growth — gives the cleanest, most chartable series for technical study, which is why it is the default view. The footer under the list confirms the active scope: Direct–Growth · daily NAV.",
                ],
            },
            {
                "heading": "Fund categories you will see",
                "paragraphs": [
                    "Categories follow SEBI's scheme classification as published by AMFI, normalised into readable labels. Use the All categories dropdown in the toolbar to narrow the list to one group.",
                    "Equity Scheme — funds that invest mainly in shares: Large Cap, Mid Cap, Small Cap, Large & Mid Cap, Multi Cap, Flexi Cap, Focused, Value / Contra, Dividend Yield, Sectoral / Thematic, and ELSS (tax-saving). Highest growth potential, highest volatility.",
                    "Hybrid Scheme — funds that mix equity and debt: Aggressive Hybrid, Conservative Hybrid, Balanced Advantage / Dynamic Asset Allocation, Multi Asset Allocation, Equity Savings, and Arbitrage. Smoother NAV lines than pure equity because the debt or hedged portion cushions falls.",
                    "Debt Scheme — bond and money-market funds: Liquid, Overnight, Ultra Short, Low Duration, Money Market, Short / Medium / Long Duration, Corporate Bond, Banking & PSU, Gilt, Credit Risk, Dynamic Bond, and Floater. NAV lines are near-straight and gently rising; the interesting signal is a break in that slope.",
                    "Other Scheme — Index Funds, ETFs, Fund of Funds (Domestic), and Overseas Fund of Funds. These track a benchmark, a commodity such as gold, or an offshore basket rather than being actively picked.",
                    "Solution Oriented — retirement and children's funds, which carry a mandatory lock-in.",
                ],
            },
            {
                "heading": "How funds differ from standalone stock symbols",
                "paragraphs": [
                    "A stock has a traded price set continuously by buyers and sellers. A fund has a NAV — the fund's total assets divided by units outstanding, computed once after market close. Nothing trades at an intraday fund price, so a NAV series has no true open, high, or low.",
                    "Charts In Motion therefore plots one NAV point per business day. Candles on a fund chart are flat by construction, and the volume pane stays empty because AMFI publishes no traded quantity for a scheme. The chart's price pane is labelled NAV rather than Price.",
                    "Timeframes start at 1D. There is no 4H option on a fund chart, and the Funds tab is excluded from live session refreshes.",
                    "A fund is a basket, not a company. There is no market cap, no P/E, no earnings date, no results beat, and no split ledger — so funds do not appear in the NSE screener, filter chips, Presets, Market Map, Market Movers, Earnings, Watchlist, Portfolio, or P&L. Those surfaces are built around per-company fundamentals that a scheme does not have.",
                    "A fund's diversification is also its ceiling: a single stock can double on one result, while a diversified equity fund moves with dozens of holdings at once. Read fund NAV charts as trend and regime evidence, not as breakout setups.",
                ],
            },
            {
                "heading": "Finding a fund — search, category, Favorites",
                "paragraphs": [
                    "Search fund… matches on scheme name, AMC name, or AMFI scheme code. Typing an AMC name (for example an fund house name) lists that house's whole Direct–Growth range.",
                    "All categories filters the list to one SEBI category — the fastest way to line up peers, for example every Mid Cap fund or every Balanced Advantage fund, before comparing their NAV charts one after another.",
                    "Favorites (★) pins the schemes you actually track. Click the star on any row to add or remove it, then use the Favorites button in the toolbar to show only starred funds. Favorites are saved per account on the server, so they follow you across sessions and machines.",
                    "Search, category, and Favorites combine — for example star ten funds, then filter to Equity Scheme - Flexi Cap within your favorites.",
                ],
            },
            {
                "heading": "The fund list",
                "paragraphs": [
                    "Each row shows the scheme name with its SEBI category underneath, the latest NAV, and the NAV date. The date column is the honest freshness check: if it is several days old, run an AMFI refresh.",
                    "Click any row to load that scheme's NAV chart on the right. The selected fund's name and its latest day change % appear in the toolbar above the chart.",
                    "Drag the divider between the list and the chart to give either side more room. The footer shows how many funds match your current filters.",
                ],
            },
            {
                "heading": "The NAV chart",
                "paragraphs": [
                    "The chart header offers D / W / M timeframe groups — 1D through 7D, 1W through 4W, and 1M through 12M. Daily NAV points are aggregated up into weekly and monthly bars, which is where fund charts become genuinely readable: a 1M view of a five-year NAV series shows regime changes that a daily line buries in noise.",
                    "EMA overlays work exactly as on stock charts. An equity fund NAV crossing below its long EMA and staying there is a slow, deliberate signal — funds do not whipsaw the way single stocks do.",
                    "Indicators offers StochRSI and MACD panes. On daily NAV they are slow-moving; most users read them on weekly or monthly bars.",
                    "Vol is present for toolbar consistency but has nothing to plot — AMFI does not publish scheme-level traded volume.",
                    "Your EMA set, volume toggle, and indicator panes are shared with the rest of the app's charts, so a fund chart opens with the same setup you use for stocks.",
                ],
            },
            {
                "heading": "How to use this page to your benefit",
                "paragraphs": [
                    "Compare peers honestly. Filter to one category, then click through funds in turn on the same timeframe. You are comparing shapes — depth of drawdown, speed of recovery, steadiness of trend — not marketing return tables computed from convenient start dates.",
                    "Check what a fund actually did in a bad stretch. Switch to a monthly view and look at the last market correction. A fund that fell less and recovered faster than its category is doing something structurally different, and that shows on the chart long before it shows in a factsheet.",
                    "Decide between direct stocks and a fund for the same idea. If you like a sector, put the sector's Thematic fund NAV next to the individual names you were considering on Market Map or NSE. The fund shows what the diversified version of the trade would have felt like.",
                    "Sanity-check a Balanced Advantage or Hybrid claim. Those funds promise a smoother ride; the NAV chart shows whether the smoothing was real.",
                    "Watch a debt fund for slope breaks. A Debt Scheme NAV should climb in a near-straight line. A visible dip is a credit or duration event and is worth investigating.",
                    "Build a shortlist you revisit. Star candidate funds, then open Favorites once a month, run through the charts on 1M, and keep the shortlist honest.",
                    "Pair it with the rest of the app. Use Market Pulse and Market Map to read what the market is doing, then use Funds to decide which vehicle — a fund or a set of stocks — you want that exposure through.",
                ],
            },
            {
                "heading": "Keeping NAVs current",
                "paragraphs": [
                    "Fund NAVs refresh through Admin → Scheduler → AMFI mutual fund NAVs. Use Run now for an immediate pull, or add a schedule so it runs itself.",
                    "The job is blocked before 15:30 IST on weekdays and will tell you so — AMFI publishes after market close, so an earlier run would only re-fetch yesterday's file. Weekends run without the gate.",
                    "If the list is empty, no AMFI download has completed yet on this install; the empty-state message points you to the same scheduler task.",
                    "NAV history for a scheme deepens on first open and then extends with each refresh, so a fund you have followed for a while will chart further back than one you just discovered.",
                ],
            },
        ],
    },
    "market-pulse": {
        "title": "Market Pulse",
        "sections": [
            {
                "heading": "What Market Pulse is for",
                "paragraphs": [
                    "Market Pulse is Charts In Motion's index-level dashboard — a single scrollable wall of NSE benchmark cards so you can see how the whole market is trading without opening each index one by one.",
                    "Each card shows the latest index level, today's change %, and how that index has performed over the past month (1M) and year (1Y). Green and red borders and badges make it easy to spot leaders and laggards at a glance.",
                    "Use it at the open of a session to answer: Which benchmarks are strong today? Which sectors are dragging? Is the move broad (many indices green) or narrow (only a few pockets of strength)? From there you can decide where to dig deeper on Indices or Market Map.",
                ],
            },
            {
                "heading": "What each card shows",
                "paragraphs": [
                    "Every card displays the index name, symbol, last traded level, and session change % in the top-right badge.",
                    "Below the price, 1M and 1Y show the index's percentage change over roughly the last month and year — useful for separating a one-day spike from a sustained trend.",
                    "Cards are colour-tinted green when the index is up on the day, red when down, and neutral when flat. Market Pulse is read-only: it does not open charts or constituents from the card itself.",
                ],
            },
            {
                "heading": "Equity Indices and Non-Chartable",
                "paragraphs": [
                    "Equity Indices — larger cards for chartable NSE equity benchmarks (Nifty 50, Bank Nifty, sector indices, and similar). These are the same indices you can chart and analyse on the Indices tab.",
                    "Equity Indices (Non-Chartable) — a compact grid of additional NSE equity indices that Charts In Motion tracks for price and performance but does not chart in-app. They still help you monitor breadth — for example niche sector or thematic indices — even when there is no dedicated index chart tab for them.",
                    "The section header shows how many indices are in each group. Scroll the page to move from headline benchmarks through the full NSE index universe.",
                ],
            },
            {
                "heading": "Market Pulse vs Market Map",
                "paragraphs": [
                    "Market Pulse is index-level only. You see many indices at once, each summarised by price and 1D / 1M / 1Y change. There are no constituent stocks, no advance–decline bars, and no heatmap tiles.",
                    "Market Map is constituent-level drill-down. You pick one index on the left, read how many stocks inside it are advancing versus declining, then explore every member in a Grid or Heatmap — filter movers, sort by % change, and click a stock to open its full chart tab.",
                    "A practical workflow: start on Market Pulse to see which benchmarks matter today → open Indices to chart a selected benchmark → open Market Map when you need to know which stocks inside that index are driving the move.",
                ],
            },
            {
                "heading": "Market Pulse vs Indices",
                "paragraphs": [
                    "Indices is the research workspace for one chartable index at a time — inline chart, indicators, multi-timeframe View, Constituents link, and Save Layout.",
                    "Market Pulse is the panorama before the microscope: scan every tracked index in seconds, then switch to Indices when you want candles, EMAs, and notes on a specific benchmark.",
                ],
            },
            {
                "heading": "Refresh",
                "paragraphs": [
                    "↻ Refresh in the tab bar reloads index levels and change percentages from the server. An Updated time in the page header shows when the last fetch completed on your screen.",
                    "Use Refresh during the session after a sharp move or when you want the latest session % before comparing indices side by side.",
                ],
            },
        ],
    },
    "market-movers": {
        "title": "Market Movers",
        "sections": [
            {
                "heading": "What Market Movers is for",
                "paragraphs": [
                    "Market Movers ranks stocks across the full NSE universe — not inside a single index. Use it to find who is moving the most on price or volume today, then inspect a name on the inline chart without building a screener first.",
                    "Unlike Market Pulse (index-level cards) or Market Map (constituents of one benchmark), Movers answers: Which stocks are the biggest gainers or losers right now? Who is trading unusual volume?",
                    "Pick a row on the left to load that symbol on the right. Use Open Full Chart ↗ for a dedicated chart tab, or right-click a row to add the symbol to Portfolio or a Watchlist.",
                ],
            },
            {
                "heading": "Ranking system",
                "paragraphs": [
                    "Day change — ranks by session % move. Gainers lists stocks with positive change, highest first. Losers lists negative change, deepest loss first. Flat names (0%) are excluded from both sides.",
                    "Volume — ranks by trading activity instead of price direction. Absolute sorts by today's share volume (highest first). Surge % sorts by how much volume rose versus the prior session. RVOL 20d sorts by today's volume relative to the 20-day average — a simple unusual-activity read.",
                    "Each mode returns a numbered Top list (20–400 names). The # column is rank within your chosen mode and filters.",
                ],
            },
            {
                "heading": "Filters and the list",
                "paragraphs": [
                    "Min MCap — optional floor so micro-caps do not dominate (type values like 500M or 50B). Top — how many ranked names to fetch. Per page — how many rows show at a time; use Prev / Next at the bottom of the list.",
                    "Live refresh — set an interval (15s to 2 minutes) and press Apply filters to poll live quotes during the session; set None for end-of-day rankings from stored OHLC. The list header shows Live status or the EOD as-of date.",
                    "Change ranking or filter settings, then press Apply filters to reload. ↻ Refresh in the tab bar also reloads the current movers list.",
                ],
            },
            {
                "heading": "Chart panel",
                "paragraphs": [
                    "The right side mirrors the NSE Dashboard chart toolbar: Vol, EMA, Indicators, View (single or multi-timeframe), drawing tools, Financials links, and Save Layout for pane width and timeframes.",
                    "During live refresh, the selected row's session change % can feed the chart header so price action stays aligned with the movers list.",
                ],
            },
        ],
    },
    "market-map": {
        "title": "Market Map",
        "sections": [
            {
                "heading": "What Market Map is for",
                "paragraphs": [
                    "Market Map is Charts In Motion's breadth and heatmap view for NSE benchmark indices. It answers two questions at once: Is this index move broad or narrow? And which member stocks are driving it?",
                    "Use it at the start of a session to scan participation across Nifty 50, Bank Nifty, sector indices, and mid/small-cap benchmarks. Pick an index on the left, read the advance/decline bar, then explore constituents on the right — spot leaders, laggards, and earnings standouts without building a custom screener first.",
                    "Click any stock tile (Grid or Heatmap) to open that symbol in a dedicated Stock Chart tab — the full chart workspace with indicators, layouts, and the same tools as Open Full Chart on the NSE Dashboard. Charts In Motion keeps up to five chart tabs; opening a sixth replaces the oldest.",
                    "When you opened the chart from Market Map, closing that chart tab returns you to Market Map instead of the NSE Dashboard.",
                ],
            },
            {
                "heading": "Index list (left)",
                "paragraphs": [
                    "The left rail lists major Nifty indices. Each row shows the index name, session change %, and a green/red advance–decline bar with counts of stocks up versus down inside that index.",
                    "Select a row to load its constituent map on the right. Drag ⋮⋮ to reorder indices; Save Layout remembers your order, pane width, and last selected index.",
                    "An “as of” timestamp in the toolbar shows when summary data was last computed.",
                ],
            },
            {
                "heading": "Grid and Heatmap",
                "paragraphs": [
                    "Grid — equal-size tiles in a scrollable grid. Every constituent gets the same tile area; colour shows 1-day change % (green up, red down). Best when you want to compare many names at a glance or use % high→low sorting.",
                    "Heatmap — a treemap where tile area reflects market cap and colour reflects 1-day change %. Larger companies occupy more space, so you see which names matter most by size as well as direction.",
                    "Switch with the Grid and Heatmap buttons in the page toolbar. Period is 1D today (additional lookback periods will be added later).",
                ],
            },
            {
                "heading": "Stocks and Sectors (Heatmap only)",
                "paragraphs": [
                    "When Heatmap is active, Stocks lays out all constituents in one treemap ranked by market cap.",
                    "Sectors groups the same constituents into NSE market-sector blocks first, then sizes stocks within each sector. Use Sectors to see which industry buckets are contributing to an index move — for example whether Nifty IT is lifting Nifty 50, or strength is spread across several sectors.",
                ],
            },
            {
                "heading": "% high→low and Sort",
                "paragraphs": [
                    "% high→low (toolbar, Grid only) — reorders tiles so the biggest gainers appear first and the deepest losers last. Missing change % sorts to the bottom.",
                    "In the detail header below the index name, Sort offers A–Z and Z–A by symbol. These sorts apply to the constituent list feeding both Grid and Heatmap.",
                    "Toolbar sort and header sort work together with filters: filters narrow the set first, then sort order is applied.",
                ],
            },
            {
                "heading": "Filter chips",
                "paragraphs": [
                    "Filter chips below the index header narrow constituents by 1-day move magnitude. Click a chip to toggle it on; click again to clear.",
                    "Gainer chips (≥+1%, ≥+3%, ≥+5%) show only stocks at or above that positive change.",
                    "Loser chips (≤−1%, ≤−3%, ≤−5%) show only stocks at or below that negative change.",
                    "Use filters to focus on meaningful movers inside a flat index — for example, only stocks down more than 3% when the headline index is only slightly red.",
                ],
            },
            {
                "heading": "Earnings (E) and Earnings+ (E+) badges",
                "paragraphs": [
                    "On Grid tiles, small corner badges highlight recent earnings context so you can spot quality and surprise without leaving the map.",
                    "E (green) — Beat EPS+Rev. The latest reported quarter beat analyst estimates on both EPS and revenue (positive surprise on each). Useful for finding names that exceeded expectations while the market is still reacting to the session move.",
                    "E+ (gold) — Earnings+ quality. Charts In Motion's quality check on Screener.in quarterly data: the latest quarter's operating margin, net profit, and EPS are all higher than the prior quarter and the same quarter last year (consolidated figures used when available). It flags improving fundamentals, not just a one-day price move.",
                    "On Heatmap, Earnings+ qualified stocks also get a gold border around the tile. Hover a tile for symbol and change %; click the tile to open the full Stock Chart tab. Badges are informational — always confirm on the chart and in the Earnings view before acting.",
                ],
            },
            {
                "heading": "Refresh and Save Layout",
                "paragraphs": [
                    "↻ Refresh in the tab bar reloads the index list and the current index's constituent heatmap from the server. Use it during the session to update prices and breadth counts.",
                    "Save Layout stores your index-list order, left-pane width, and which index was selected.",
                ],
            },
        ],
    },
    "earnings-beats": {
        "title": "Earnings",
        "sections": [
            {
                "heading": "What the Earnings page is for",
                "paragraphs": [
                    "The Earnings page is Charts In Motion's earnings calendar for NSE stocks — reported results with EPS and revenue surprise versus estimates, and upcoming report dates with analyst estimates.",
                    "Use Reported to review who beat or missed this month (or any past month in the year). Use Upcoming to see who reports in this month, next month, the month after, or the coming week.",
                    "The table shows market cap, price, 1-day and 2-week change, and surprise columns. Click a row to select it; double-click or use ▶ to expand Screener.in quarterly results inline. The footer opens Chart, Screener, TradingView overview, and TV Earnings for the selected symbol. Right-click a row for Portfolio or Watchlist actions.",
                    "Column headers sort the loaded list. Your filter choices are remembered on this device. ↻ Refresh in the tab bar reloads the table with current filters.",
                ],
            },
            {
                "heading": "Filter sections",
                "paragraphs": [
                    "Earnings — switch between Reported (results already announced) and Upcoming (scheduled dates).",
                    "Year and Month (Reported) — pick the calendar year and month of the earnings release. All months loads every reported name in that year. Future months in the current year are disabled until results exist.",
                    "Period (Upcoming) — This month, Next month, Month after, or Coming week instead of a fixed month picker.",
                    "MCap min / Max — optional market-cap floor or ceiling. Type values with M, B, or T (e.g. 500M, 50B). Empty means no bound. Helps focus on large caps or exclude micro-caps when scanning surprises.",
                    "EPS beat min % / Max % (Reported only) — filter by EPS surprise versus estimate. Empty = no bound. Min 0 includes names that met estimates exactly (0% surprise). Use a positive min to find clear beats; a negative max to find misses.",
                    "Rev beat min % / Max % (Reported only) — same idea for revenue surprise. Combine with EPS filters to find dual beats (both EPS and revenue above your thresholds).",
                    "Earnings+ (Reported only) — All, Earnings+ only, or Exclude Earnings+. Earnings+ is Charts In Motion's quality badge from Screener quarterly data: latest quarter OPM, net profit, and EPS higher than the prior quarter and the same quarter last year (consolidated when available). This is separate from beating analyst estimates — a stock can beat EPS estimates without qualifying for Earnings+.",
                    "Search symbol or name — narrows the already-loaded table without changing server filters.",
                ],
            },
            {
                "heading": "Fetch latest data",
                "paragraphs": [
                    "Fetch latest data bypasses Charts In Motion's cached TradingView earnings scan and pulls a fresh calendar for your current filters. Use it when you expect new reports to have landed and the table looks stale.",
                    "This updates the earnings list only. It does not rebuild the Earnings+ quality cache — use the Earnings+ cache buttons for that.",
                ],
            },
            {
                "heading": "Refresh Earnings+ cache",
                "paragraphs": [
                    "Refresh Earnings+ cache warms the database-backed Earnings+ verdicts for every symbol in the selected Reported month. Charts In Motion uses stored Screener quarterly data when it is already on disk; only missing or outdated rows are recomputed.",
                    "You need a warm cache before Earnings+ only / Exclude Earnings+ filters are complete. The status line under the filters shows uncached or stale counts when applicable.",
                    "While the job runs, progress appears in the Update panel. When it finishes, the table reloads for the month that was refreshed.",
                ],
            },
            {
                "heading": "Retry incomplete and Force all",
                "paragraphs": [
                    "Retry incomplete — runs the same Earnings+ cache job but only for symbols with no cache row yet or with insufficient_data (Screener quarterly data could not be evaluated). Use this after a partial run or when a few names still show as uncached.",
                    "Force all — recomputes Earnings+ for every reported symbol in the selected month and may re-scrape Screener quarterly data even when a verdict already exists. Slower; Charts In Motion asks you to confirm before starting. Reserve for after Screener data fixes or when you suspect cached verdicts are wrong.",
                ],
            },
            {
                "heading": "Settings cog: Refresh Earnings+ Cache (This Month)",
                "paragraphs": [
                    "Open the ⚙ settings menu in the tab bar and choose Refresh Earnings+ Cache (This Month). It starts the same background job as Refresh Earnings+ cache on the Earnings page, but always targets the current calendar month — regardless of which month you are viewing on the page.",
                    "Useful when you are browsing a past month on Earnings but still want to warm this month's Earnings+ badges for Market Map, Portfolio highlights, and filters without changing Year/Month first.",
                ],
            },
            {
                "heading": "Status line and background warm",
                "paragraphs": [
                    "Below the filters, the status line shows the active mode and period, stock count, whether the earnings scan was served from cache, and the last fetch time.",
                    "When relevant, it also shows Earnings+ cache gaps (uncached / stale) and Last background warm — Charts In Motion periodically warms Earnings+ during market hours even when you are not on this page. That line is informational; use the refresh buttons when you need an immediate update for the month you are studying.",
                ],
            },
        ],
    },
    "dashboard": {
        "title": "NSE Dashboard",
        "sections": [
            {
                "heading": "What this view shows",
                "paragraphs": [
                    "The NSE Dashboard is Charts In Motion's primary stock screener and research workspace. A sortable stock table on the left pairs with an inline chart on the right so you can scan the universe, filter by technical and fundamental criteria, and inspect price action without leaving the page.",
                    "Click any row to load that symbol in the chart panel. Use Open Full Chart ↗ to open the selection in a dedicated chart tab. Charts In Motion keeps five chart tabs open at a time — opening a sixth replaces the oldest tab (the one you opened earliest), not the tab you are currently viewing.",
                ],
            },
            {
                "heading": "Stock table",
                "paragraphs": [
                    "Columns include Symbol, Market Cap (M/B/T), Price, 1-day change %, and 1-month change %. Click a column header to sort ascending or descending; the default sort is Market Cap, largest first.",
                    "The footer shows how many stocks match your current view. Without active filters, the list loads in pages as you scroll. When filters or sector picks are active, Charts In Motion loads the full matching set so counts and watchlist actions stay accurate.",
                    "Select multiple rows with Ctrl+click (Cmd+click on Mac) or Shift+click for a range. Right-click a row for quick actions — add to Portfolio, add to a Watchlist, or create a new watchlist on the spot.",
                ],
            },
            {
                "heading": "Search",
                "paragraphs": [
                    "The Search symbol… box in the chart toolbar filters the stock table and opens a dropdown of matching stocks and indices from the full universe. Pick a result to jump straight to that symbol even if it is not in the current filtered list.",
                    "From anywhere in the app (when your cursor is not in a text field), start typing a symbol to open global search. Arrow keys move through results; Enter selects. Escape closes the palette.",
                ],
            },
            {
                "heading": "Screener filters",
                "paragraphs": [
                    "Click + Filter to add criteria. Active filters appear as chips in the filter bar. Click a chip to edit it, toggle the dot to enable or disable without removing it, or use the × to delete. Clear all removes every filter at once.",
                    "EMA — compare an EMA to price, open/high/low, or another EMA on daily, weekly, or monthly timeframes. Conditions include above/below, crosses, and percentage distance.",
                    "MACD and StochRSI — same condition vocabulary (above, below, crosses, % distance) applied to indicator levels or their signal lines on your chosen timeframe.",
                    "MACD Histogram — chain filter for consecutive bars moving toward or away from zero, with controls for bar count, allowed stragglers, positive/negative side, and zero-cross behaviour.",
                    "Price — test where price sits relative to an EMA or to the session open, high, or low.",
                    "Market Cap — set a minimum, maximum, or range. You can type values with M, B, or T suffixes (e.g. 500M, 2B).",
                    "Earnings — narrow by reporting window (this week, previous week, or a custom month range) and optional EPS or revenue surprise bounds.",
                ],
            },
            {
                "heading": "Sector filter and presets",
                "paragraphs": [
                    "Sector (in the chart toolbar) limits both the stock table and technical scans to one or more market sectors. Select multiple sectors; the badge shows how many are active. Clear resets the pick. Sector names are managed under Data Management if you need to adjust mappings.",
                    "Presets save your current filter chips for reuse. Load a saved preset from the Presets menu, tweak filters, then Update preset when the name is highlighted. Use ✦ Save to store a new preset. Click the pen icon on a row to rename a preset inline. The Backup row at the bottom exports or imports all presets as JSON — useful when moving between machines.",
                ],
            },
            {
                "heading": "Watchlist from scan results",
                "paragraphs": [
                    "When filters or sector picks are active, the Watchlist button appears in the filter bar. Add the selected symbol to a list, or use Add all to… to push every stock in the current filtered result into a watchlist.",
                    "If you have no watchlists yet, Charts In Motion will prompt you to create one on the Watchlist tab first.",
                ],
            },
            {
                "heading": "Chart toolbar: symbol, Vol, and EMA",
                "paragraphs": [
                    "When a row is selected, the chart toolbar shows the symbol, its market sector, the latest price, and session change (from the chart crosshair when available).",
                    "Vol toggles the volume histogram under the price chart. EMA opens the overlay editor — add or remove EMA periods, change colours, and show or hide each line. EMA settings are shared across Charts In Motion charts on this device.",
                    "The drawing-tools control (pencil icon) opens trend lines and annotations on the inline chart. In multi-timeframe View layouts, drawings can mirror across panels so marks stay aligned on the same symbol.",
                ],
            },
            {
                "heading": "View (chart layout)",
                "paragraphs": [
                    "View, on the right side of the chart toolbar, controls how many timeframe panels appear for the selected symbol.",
                    "Single — one chart panel (default). Use the timeframe control in the chart header to change interval (e.g. 1D, 1W, 1M).",
                    "2 — Multi Timeframe — the same stock side by side in two panels, each with its own timeframe. Useful for comparing daily structure against weekly or monthly trend.",
                    "3 — Multi Timeframe — three panels for the same symbol. Compare short-, medium-, and long-term structure without opening extra tabs.",
                ],
            },
            {
                "heading": "Indicators",
                "paragraphs": [
                    "Indicators opens a menu for sub-panels below the price chart: StochRSI and MACD. Check a name to show it; uncheck to hide. Your choices persist across Charts In Motion chart views.",
                    "These panels read from Charts In Motion indicator snapshots — the same data that powers screener filters — so what you see in the list filter should match what appears on the chart after snapshots are updated.",
                    "Reorder panels by drag handles inside the chart area when multiple indicator panels are visible.",
                ],
            },
            {
                "heading": "Open Full Chart",
                "paragraphs": [
                    "Open Full Chart ↗ promotes the selected symbol from the inline panel to a dedicated chart tab in the main tab bar (alongside NSE, Indices, and your other open charts).",
                    "Use it when you want more horizontal space, a focused workspace, or to keep several symbols in chart tabs while continuing to screen on the NSE Dashboard.",
                    "Charts In Motion keeps five chart tabs open at a time. Opening a sixth replaces the oldest chart tab — the one you opened earliest — not the tab you are currently viewing.",
                ],
            },
            {
                "heading": "Save Layout",
                "paragraphs": [
                    "Save Layout stores your current NSE Dashboard workspace to the server: stock-list pane width, View layout (Single / 2 / 3), all three timeframe selections, and chart panel height ratios.",
                    "Click Save Layout after resizing the list/chart divider or changing View or timeframes so your setup is restored next time you open Charts In Motion on this machine.",
                    "A brief toast confirms success or failure. Save Layout does not store screener filter presets — use Presets in the filter bar for those.",
                ],
            },
            {
                "heading": "Financials dropdown",
                "paragraphs": [
                    "Financials appears in the chart toolbar when a stock row is selected (not for indices). It is placed next to the symbol because every link is built from the currently selected ticker — you never re-type the symbol on another site.",
                    "Open the menu to jump out to third-party research pages in a new browser tab: Screener ↗ opens that company's quarterly results and ratios on Screener.in; TradingView ↗ opens the NSE symbol's financials overview on TradingView India.",
                    "Why it is here: Charts In Motion focuses on screening and charting; Screener.in and TradingView carry deeper fundamental tables, peer context, and historical financials that are not duplicated inside Charts In Motion. The dropdown bridges technical work on the dashboard with fundamental due diligence in one click.",
                    "Typical workflow: filter or sort the table, select a name, glance at the inline chart, then open Financials → Screener to read recent quarters or TradingView for a consolidated financial snapshot — without leaving your place in the screener list.",
                ],
            },
            {
                "heading": "Refresh and Update (tab bar)",
                "paragraphs": [
                    "↻ Refresh reloads the current page's live table data from the server. On NSE Dashboard that means refreshed prices, changes, and market cap for the stock list — a quick pull, not a full data rebuild.",
                    "Update opens a menu of heavier server jobs that refresh the datasets Charts In Motion charts and screeners depend on:",
                    "Update price and volume data — downloads/refreshes raw OHLCV history used by charts. This is chart data, not filter snapshots.",
                    "Repair Index Chart Gaps — on-demand scan and backfill for missing index daily bars (NSE official history, Yahoo fallback). Run when index charts show long calendar gaps; not part of the regular price/volume update.",
                    "Filter rebuild — in Admin Scheduler, add one or more filter schedules (weekday frequency, incremental or full mode) for precomputed filter snapshots such as price OHLC, EMA, MACD, StochRSI, average volume, and range channel. Other jobs (Fetch chart data, EOD bhavcopy, etc.) also support multiple schedules at different times of day.",
                    "Apply pending split adjustments — adjusts price history for symbols in the split ledger.",
                    "Catch-up split scan (90 days) — finds recent splits and marks already-adjusted history without a full re-download.",
                    "Refresh share counts (market cap basis) — Yahoo → Screener.in issued share counts for market-cap (shares × price); run after splits or periodically.",
                    "While a job runs, the Update button shows progress; click it again to open the progress panel.",
                    "For scheduled or off-peak jobs (chart data fetch, filter rebuild, EOD reconcile, split watch, earnings warm, and more), use Admin Scheduler in the Settings (⚙) menu on the showcase host. Every task is opt-in — nothing runs on a timer until you enable it and save.",
                ],
            },
            {
                "heading": "Admin Scheduler (showcase host)",
                "paragraphs": [
                    "Open Settings → Admin Scheduler (or Update → Admin Scheduler) when signed in as operator.",
                    "Tasks include fetch chart data (OHLCV), filter rebuild (multiple schedules with weekday frequency and incremental/full mode), EOD reconcile, live quotes warm, split watch, earnings warm, fetch financials, screener sector fill, and expand universe.",
                    "Run now starts a task immediately for rare forced runs. Enable saves a daily or weekly IST time (or an interval for chart data fetch) and lists the task under Active schedules. Filter rebuild supports + New Schedule for additional filter jobs.",
                    "The scheduler log and current activity appear at the top. Only one heavy job runs at a time.",
                ],
            },
            {
                "heading": "Settings (⚙ cog menu)",
                "paragraphs": [
                    "The cog icon at the far right of the tab bar opens application settings and maintenance actions:",
                    "Aggressive Cache (RAM) — keeps more chart and API data in memory for speed; uses more RAM. The icon turns red when enabled.",
                    "Clear Cache Now — flushes cached data if charts or tables look stale after a manual fix.",
                    "Refresh Earnings+ Cache (This Month) — refreshes consolidated earnings figures used by the Earnings view and earnings-related filters.",
                    "Rebuild Indicator Snapshots — full rebuild of indicator snapshot data (slower than incremental Update; use when snapshots look widely wrong).",
                    "Data Management — edit sector mappings and related reference data (also linked from the Sector filter menu).",
                    "Report Issue / Feature Request — send feedback via Google Forms.",
                    "Update App — install a pending Charts In Motion desktop update when one is available.",
                    "Support the Development — optional support link.",
                ],
            },
            {
                "heading": "Notes and layout",
                "paragraphs": [
                    "The notes icon in the Symbol column opens a per-instrument memo (saved on this device for your account). A filled icon means a note already exists.",
                    "Drag the vertical divider between the stock table and chart to resize the list pane. Click Save Layout to remember that width together with your View and timeframe choices.",
                ],
            },
        ],
    },
    "indices": {
        "title": "Indices",
        "sections": [
            {
                "heading": "What this view shows",
                "paragraphs": [
                    "Indices is Charts In Motion's workspace for NSE equity benchmarks and sector indices — Nifty 50, Bank Nifty, sectoral indices, and similar chartable benchmarks in one place.",
                    "The layout matches the NSE Dashboard: an index list on the left and an inline index chart on the right. Select any index to plot its history, toggle indicators, and compare timeframes without leaving the tab.",
                ],
            },
            {
                "heading": "Index list",
                "paragraphs": [
                    "The Equity section lists chartable equity indices with name, latest level, and session change %. The selected row is highlighted in blue.",
                    "Drag the ⋮⋮ handle to reorder indices in the list. Your custom order is saved when you click Save Layout.",
                    "The notes icon on each row opens a private memo for that index (stored on this device for your account). Right-click a row for quick actions such as adding the index to Portfolio or a Watchlist.",
                ],
            },
            {
                "heading": "Search and keyboard navigation",
                "paragraphs": [
                    "Search index… filters the equity list by symbol or name.",
                    "Use ↑ and ↓ arrow keys to move through the filtered list; the chart updates to follow the highlighted index.",
                    "From the Indices tab, you can also start typing a symbol to use global search — matching indices jump into focus when picked.",
                ],
            },
            {
                "heading": "Inline index chart",
                "paragraphs": [
                    "The chart panel plots OHLCV history for the selected index. Change interval from the timeframe control in the chart header (e.g. 1D, 1W, 1M).",
                    "Vol toggles the volume panel. EMA opens the overlay editor for moving-average lines (shared with other Charts In Motion charts).",
                    "The drawing-tools control (pencil icon) adds trend lines and annotations on the index chart.",
                    "Drag the vertical divider to resize the list versus chart area.",
                ],
            },
            {
                "heading": "View, Indicators, and Save Layout",
                "paragraphs": [
                    "View switches the chart layout: Single (one panel), 2 — Multi Timeframe (two intervals side by side for the same index), or 3 — Multi Timeframe (three intervals).",
                    "Indicators toggles StochRSI and MACD sub-panels below the price chart.",
                    "Save Layout stores your list width, chart layout, timeframe selections, panel height ratios, and custom index list order.",
                ],
            },
            {
                "heading": "Constituents",
                "paragraphs": [
                    "For equity indices, Constituents ↗ in the chart toolbar opens that index's member stocks in a dedicated tab in the main tab bar (labelled with the index name and “Const.”).",
                    "Use Constituents to see which stocks make up the index and how each member is trading — helpful when an index is moving and you want to know which names are driving it.",
                    "If a Constituents tab for that index is already open, clicking the button switches to it. Close the tab with × when finished; you return to Indices or any other open index tab.",
                    "Open the Knowledge Base panel while on a constituents tab for full detail on the member table, sorting, and per-stock charts.",
                ],
            },
            {
                "heading": "Refresh",
                "paragraphs": [
                    "↻ Refresh in the tab bar reloads index levels and session changes from the server. Use it during the trading day to update list prices without running a full Update job.",
                ],
            },
        ],
    },
    "watchlist": {
        "title": "Watchlist",
        "sections": [
            {
                "heading": "What the Watchlist is for",
                "paragraphs": [
                    "Watchlists are your personal shortlists inside Charts In Motion — curated sets of NSE stocks and indices you want to monitor without running a full screener every time.",
                    "Use them to group names by theme (e.g. banks, IT leaders, index benchmarks), track ideas from the NSE Dashboard or Market Map, and follow price action on a dedicated table plus inline chart.",
                    "Each watchlist is saved on the server. You can maintain several lists, switch between them, and keep a different symbol order in each one.",
                ],
            },
            {
                "heading": "Layout and everyday use",
                "paragraphs": [
                    "The left panel lists symbols with market cap, price, 1-day and 1-month change. Click a row to load that stock or index on the right-hand chart (Vol, EMA, Indicators, View, drawings, Save Layout — same family as NSE Dashboard).",
                    "Stocks open Open Full Chart ↗; indices open Constituents ↗. Use × on a row to remove a symbol from the active list.",
                    "Search symbol… in the top toolbar finds stocks and indices across the universe. Pick a result to select it if it is already in the list, or use + Add to put it into the active watchlist.",
                    "Right-click symbols on NSE Dashboard, Market Map, Market Movers, Earnings, and elsewhere to add them to an existing watchlist or create a new one. Charts In Motion also adds scan results in bulk from the NSE filter bar (Add all to…).",
                ],
            },
            {
                "heading": "Manual, A–Z, and Z–A",
                "paragraphs": [
                    "Manual, A–Z, and Z–A control how your watchlist names appear in the watchlist picker — not the symbols inside the table.",
                    "Manual — lists appear in the order you set by dragging (see below). This is the default and the only mode where you can rearrange watchlists.",
                    "A–Z — sorts watchlist names alphabetically ascending for quick lookup when you have many lists.",
                    "Z–A — sorts watchlist names alphabetically descending.",
                    "Switching to A–Z or Z–A is a display sort only; switch back to Manual when you want your custom list order again.",
                ],
            },
            {
                "heading": "Select and rearrange watchlists",
                "paragraphs": [
                    "Open the watchlist dropdown (the button showing the current list name) to see all your watchlists. Click a name to make it active.",
                    "In Manual mode, when you have two or more watchlists, each row in the dropdown shows a ⋮⋮ handle. Drag a row up or down to reorder your watchlists; Charts In Motion saves the new order to the server.",
                    "Rearranging watchlists is useful when you want your most-used list at the top of the picker or a fixed personal order that A–Z would break.",
                ],
            },
            {
                "heading": "Create, rename, and delete",
                "paragraphs": [
                    "Create — type a name in New watchlist… and press Enter or click Create. The new list becomes active immediately.",
                    "Rename — open the watchlist dropdown, click the pen icon on the row you want to change, edit the name inline, then ✓ or Enter. Escape or × cancels. Your saved symbol order for that list is kept under the new name.",
                    "Delete — click the × on a row in the watchlist dropdown (confirmation required). If you delete the active list, Charts In Motion selects another list automatically when one remains.",
                ],
            },
            {
                "heading": "Export and Import",
                "paragraphs": [
                    "Open the watchlist dropdown and use the Backup row at the bottom — Export and Import — the same pattern as Presets on NSE Dashboard.",
                    "Export downloads a JSON backup of all your watchlists — every list name, its stocks and indices, and your saved manual symbol order (⋮⋮ row order) per list. Use it to move lists to another machine or keep an offline copy.",
                    "Import reads a Charts In Motion watchlist JSON file (or a plain array of watchlists). Charts In Motion asks whether to REPLACE all existing watchlists or MERGE: merge keeps lists that are not in the file and overwrites lists that share the same name; replace clears everything and loads only what is in the file.",
                    "Imported symbol order is restored when the file includes watchlist_item_order. After import, your lists appear in the picker immediately — no need to recreate them by hand.",
                ],
            },
            {
                "heading": "Reorder symbols inside a list",
                "paragraphs": [
                    "Drag the ⋮⋮ handle on a symbol row to reorder items within the active watchlist. Order is saved per list and restored when you return.",
                    "Click a column header (Symbol, Mkt Cap, Price, 1D Chg %, 1M Chg %) to sort the table by that field; click again to reverse direction. Column sort turns off Earnings priority (see below). Dragging a row switches back to your manual symbol order.",
                ],
            },
            {
                "heading": "Earnings priority (footer)",
                "paragraphs": [
                    "At the bottom of the symbol list, Earnings priority is an automatic sort that floats earnings-related names to the top so you do not miss report dates or fresh beats inside a long watchlist. It is especially useful during earnings season — when many of your watchlist stocks have just released quarterly results — because it keeps those names in focus at the top while you review beats, misses, and the market reaction.",
                    "When enabled (blue text, on by default for each list), rows reorder in three bands: (1) Upcoming earnings — stocks reporting within the next 20 days, amber highlight and E <date> under the symbol; (2) Recent Beat EPS+Rev — dual beat on EPS and revenue in the last 10 days, green highlight; (3) Everything else — keeps your underlying order (manual drag order or column sort).",
                    "Click Earnings priority ▲ or ▼ in the footer to flip date direction inside the upcoming and beat bands — ▲ nearest dates first (reporting soonest or most recently reported at the top), ▼ furthest dates first. Click again when it is greyed out to turn priority sorting back on.",
                    "The footer also shows counts when applicable — e.g. “3 beat EPS+Rev (10d)” and “5 reporting in 20 days”. Click the symbol on a highlighted row to open quarterly results and company profile. Indices are not included in earnings priority; only watchlist stocks are checked.",
                ],
            },
            {
                "heading": "Refresh and layout",
                "paragraphs": [
                    "↻ Refresh in the tab bar reloads price and change data for watchlist symbols.",
                    "Save Layout stores pane width, chart View/timeframes, and symbol order for the active watchlist.",
                ],
            },
        ],
    },
    "portfolio": {
        "title": "Portfolio",
        "sections": [
            {
                "heading": "What Portfolio is for",
                "paragraphs": [
                    "Portfolio is your invested list in Charts In Motion — a single place to keep the NSE stocks (and indices) you hold or care about as actual positions, separate from watchlists used for ideas and scans.",
                    "Use it to monitor price, market cap, and session change for names you own, open an inline chart for each holding, and stay on top of earnings during results season. The layout matches the NSE Dashboard: holdings table on the left, chart on the right.",
                    "Right-click any stock or index elsewhere in the app and choose Add to portfolio. On the Portfolio tab itself, right-click a row and choose Delete from portfolio to remove a symbol.",
                ],
            },
            {
                "heading": "Filters and Presets",
                "paragraphs": [
                    "Portfolio uses the same filter bar and Presets menu as the NSE Dashboard — + Filter, filter chips, Sector in the chart toolbar, and Search symbol… — but every filter runs only inside your portfolio holdings, not the full NSE universe.",
                    "Use filters to answer questions like “Which of my stocks are above the 200-day EMA?” or “Which holdings reported earnings this month?” without scanning the entire market. Active chips can be edited, toggled, or cleared the same way as on NSE.",
                    "Presets saves a named set of filter chips for reuse on Portfolio or NSE. Open Presets, click a saved name to load it, tweak filters, then Update preset when the name is highlighted, or use ✦ Save to store a new one. Click the pen icon on a row to rename a preset inline. The Backup row at the bottom of the Presets menu exports or imports all presets as JSON — handy when moving setups between machines. Presets are shared: a preset saved on NSE is available on Portfolio and vice versa.",
                ],
            },
            {
                "heading": "Table, chart, and row order",
                "paragraphs": [
                    "Click a row to chart that holding. Stocks support Open Full Chart ↗; indices support Constituents ↗. Vol, EMA, Indicators, View, Financials, drawing tools, and Save Layout work the same as on the NSE Dashboard.",
                    "Portfolio columns include Entry (your cost basis per holding) and P/L % (gain or loss vs current price). Click Entry to type a price; P/L updates automatically. Sort by Entry or P/L % from the column headers.",
                    "When a stock has open P&L lots, Entry on Portfolio is kept in sync with P&L — weighted average of your open buy prices. P&L is the source of truth; editing Entry on Portfolio for those symbols will reflect the P&L value instead.",
                    "Drag ⋮⋮ on a row to set a custom order among your holdings; column-header sort (Symbol, Market Cap, Price, Entry, P/L %, change %) sorts temporarily and turns off Earnings priority until you drag again or re-enable priority.",
                    "↻ Refresh in the tab bar reloads quotes and change % for portfolio symbols.",
                ],
            },
            {
                "heading": "Earnings priority (footer)",
                "paragraphs": [
                    "At the bottom of the holdings list, Earnings priority is an automatic sort that floats earnings-related names to the top so you do not miss report dates or fresh beats inside a long portfolio. It is especially useful during earnings season — when many of your holdings have just released quarterly results — because it keeps those names in focus at the top while you review beats, misses, and the market reaction.",
                    "When enabled (blue text, on by default), rows reorder in three bands: (1) Upcoming earnings — stocks reporting within the next 30 days, amber highlight and E <date> under the symbol; (2) Recent Beat EPS+Rev — dual beat on EPS and revenue in the last 10 days, green highlight; (3) Everything else — keeps your underlying order (manual drag order or column sort).",
                    "Click Earnings priority ▲ or ▼ in the footer to flip date direction inside the upcoming and beat bands — ▲ nearest dates first (reporting soonest or most recently reported at the top), ▼ furthest dates first. Click again when it is greyed out to turn priority sorting back on.",
                    "The footer also shows counts when applicable — e.g. “3 beat EPS+Rev (10d)” and “5 reporting in 30 days”. Click the symbol on a highlighted row to open quarterly results and company profile. Indices are not included in earnings priority; only portfolio stocks are checked.",
                ],
            },
        ],
    },
    "pnl": {
        "title": "P&L",
        "sections": [
            {
                "heading": "What P&L is for",
                "paragraphs": [
                    "P&L tracks realized and unrealized profit and loss on your Portfolio stocks. Use Add stock to add a symbol to Portfolio and open a lot in one step. Charts In Motion does not pull live quotes on this page.",
                    "The top half is split: open positions on the left (Book, entry, qty) and a Period panel on the right. Drag the divider between them to resize. Pick year, month, and day (or All for the whole month) to see symbols you bought or sold in that window, with realized and unrealized P/L, invested amounts, and sale proceeds. Export CSV is on the top row next to Period.",
                    "Price, market cap, and 1D / 1M change % use stored data from your last admin update (EOD or mid-session screener sync). The toolbar shows Prices as of <date> when available.",
                ],
            },
            {
                "heading": "Open positions (top grid)",
                "paragraphs": [
                    "Symbols group under one header; expand to see each dated lot (Bought column). Add stock and Add lot both require a buy date. Multiple purchases at different prices show as separate sub-rows.",
                    "Portfolio stocks without a saved lot show a placeholder row — set Entry and Qty to create the position (buy date defaults to today). Book on the symbol header sells oldest lots first (FIFO).",
                    "When you add or edit a P&L lot, Portfolio Entry for that symbol updates to match (weighted average when you have multiple lots).",
                    "When every open lot for a symbol is fully booked (qty sold = 0), the symbol is removed from this grid and from Portfolio automatically — on the same Book action, or repaired on the next P&L / Portfolio load if they ever drift.",
                ],
            },
            {
                "heading": "Book and closed trades (bottom)",
                "paragraphs": [
                    "Click Book on a symbol row. Enter exit price, qty to sell, and sale date. Charts In Motion allocates the sale across your oldest open lots first — partial sells spanning two buy dates create separate closed lines.",
                    "Profit (green header) and Loss (red header) show section totals in full rupee figures. Each symbol groups under one header with dated sub-rows; a divider marks a fresh cycle after you re-buy following a full exit.",
                    "Re-buying the same symbol after a full close starts a new open cycle on top; booked history remains below.",
                ],
            },
            {
                "heading": "Zerodha import (tradebook, holdings, positions)",
                "paragraphs": [
                    "Import CSV on the Period panel opens the Zerodha import dialog. Attach three optional files: Tradebook (required) for historical FIFO through yesterday; Holdings for open qty and average entry (fixes bonus/split drift vs Kite); Positions for today's session only (same-day sells missing from tradebook until tomorrow).",
                    "Enable Sync open to holdings when you attach a holdings file — CiM replaces open lots to match broker qty and avg. Enable Apply today's positions when you attach Kite Positions export the same day. Corp actions (e.g. TRENT 1:2 bonus) apply automatically from the registry when enabled.",
                    "Rebuild symbols in file wipes and replays open + closed history for every symbol in the tradebook — use only with a full export to fix a bad prior import. Append mode skips trade_ids already imported.",
                    "Replace Zerodha P&L treats the uploaded Tax/Console P&L as the complete Zerodha source of truth. After confirmation, CiM removes all existing Zerodha open and closed rows, rebuilds them from the upload, and optionally uses Holdings as the final open-position snapshot. Paytm and Manual records are not changed.",
                    "Sync holdings (without re-importing tradebook) updates open lots only from a holdings CSV — closed trades are untouched.",
                    "Same-day sells: if open qty still exceeds holdings after import, attach today's Positions CSV and enable Apply today's positions.",
                ],
            },
        ],
    },
    "potential-swings": {
        "title": "Potential Swings",
        "sections": [{
            "heading": "What this view shows",
            "paragraphs": [
                "Potential Swings flags symbols meeting swing-trading criteria from indicator snapshots.",
                "Results are exploratory, not investment advice — always confirm on the chart before acting.",
            ],
        }],
    },
    "chart": {
        "title": "Stock Chart",
        "sections": [{
            "heading": "What this view shows",
            "paragraphs": [
                "Stock charts support multiple layouts, EMA overlays, volume panels, and split views. Each symbol opens in its own chart tab. Charts In Motion keeps five chart tabs open at a time — opening a sixth replaces the oldest tab, not the tab you are currently viewing.",
                "Indicator snapshots and corporate actions feed the overlays; use the chart toolbar to change interval and layout.",
            ],
        }],
    },
    "index-chart": {
        "title": "Index Chart",
        "sections": [{
            "heading": "What this view shows",
            "paragraphs": [
                "Index charts plot benchmark and sector index history with the same tooling as stock charts.",
                "Open from the Indices page or Market Pulse; tabs stay pinned until you close them.",
            ],
        }],
    },
    "constituents": {
        "title": "Index Constituents",
        "sections": [
            {
                "heading": "What this view shows",
                "paragraphs": [
                    "Index Constituents breaks a benchmark index into its member stocks — every symbol in that index with live price, market cap, and performance columns on the left, and an inline stock chart on the right.",
                    "It answers: “The index is up or down — which stocks inside it are actually moving?” Scan the table, click a name, and inspect its chart without losing the index context.",
                ],
            },
            {
                "heading": "How to open Constituents",
                "paragraphs": [
                    "On the Indices tab, select an equity index (e.g. Nifty 50) and click Constituents ↗ in the chart toolbar. Charts In Motion opens a new tab in the main tab bar named after the index (e.g. “Nifty 50 — Const.”).",
                    "You can also reach Constituents from a Watchlist when the selected item is an index that supports constituents.",
                    "← [Index name] in the constituents toolbar returns you to the related index chart tab if one is open, otherwise back to the Indices list.",
                ],
            },
            {
                "heading": "Constituents table",
                "paragraphs": [
                    "Columns include Symbol, Market Cap (M/B/T), Price, 1-day change %, 30-day change %, 1-year change %, and Volume. Click a column header to sort; click again to reverse direction.",
                    "The Filter… box narrows rows by symbol or company name. The footer shows how many stocks match and reminds you that ↑↓ keys move selection.",
                    "The notes icon opens a private per-stock memo (stored on this device for your account). Right-click a row to add the stock to Portfolio or a Watchlist.",
                ],
            },
            {
                "heading": "Inline stock chart",
                "paragraphs": [
                    "Click any row (or use ↑↓) to load that stock in the chart panel. Vol and EMA work the same as on the NSE Dashboard.",
                    "View offers Single, 2 — Multi Timeframe, or 3 — Multi Timeframe layouts for the selected constituent.",
                    "Drawing tools are available on the inline chart. Drag the divider to give more room to the table or the chart.",
                ],
            },
            {
                "heading": "Financials and Open Full Chart",
                "paragraphs": [
                    "Financials (when a stock is selected) links to Screener.in and TradingView for that symbol — useful for reading quarterly results on a name you found inside the index.",
                    "Open Full Chart ↗ promotes the selected constituent to a dedicated stock chart tab so you can keep analysing it while the constituents tab stays open on the index.",
                ],
            },
            {
                "heading": "When to use Constituents",
                "paragraphs": [
                    "After a sharp index move — sort by 1D Chg % to see leaders and laggards inside the benchmark.",
                    "When screening by market cap within an index — sort by Mkt Cap to focus on the largest weights first.",
                    "Before adding index exposure — check whether a few names dominate the day's move or breadth is wide across members.",
                ],
            },
        ],
    },
}


def default_page(guide_id: str) -> dict[str, Any]:
    stub = PAGE_STUBS.get(guide_id)
    if stub:
        return {
            "title": stub["title"],
            "sections": [dict(s) for s in stub["sections"]],
        }
    label = KB_PAGE_LABELS.get(guide_id, guide_id)
    return {
        "title": label,
        "sections": [{
            "heading": "Overview",
            "paragraphs": ["Add content for this page in the Knowledge Base editor (dev only)."],
        }],
    }


def default_document() -> dict[str, Any]:
    return {
        "version": 1,
        "pages": {pid: default_page(pid) for pid in KB_PAGE_IDS},
    }


def _normalize_section(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    heading = str(raw.get("heading") or "").strip()
    paragraphs_in = raw.get("paragraphs")
    if not heading:
        return None
    paragraphs: list[str] = []
    if isinstance(paragraphs_in, list):
        for p in paragraphs_in:
            text = str(p or "").strip()
            if text:
                paragraphs.append(text)
    if not paragraphs:
        paragraphs = [""]
    return {"heading": heading, "paragraphs": paragraphs}


def normalize_page(raw: Any, guide_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return default_page(guide_id)
    title = str(raw.get("title") or KB_PAGE_LABELS.get(guide_id, guide_id)).strip()
    sections_in = raw.get("sections")
    sections: list[dict[str, Any]] = []
    if isinstance(sections_in, list):
        for item in sections_in:
            sec = _normalize_section(item)
            if sec:
                sections.append(sec)
    if not sections:
        sections = [dict(DEFAULT_SECTION)]
    return {"title": title or KB_PAGE_LABELS.get(guide_id, guide_id), "sections": sections}


def normalize_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return default_document()
    pages_in = raw.get("pages")
    pages: dict[str, Any] = {}
    if isinstance(pages_in, dict):
        for pid in KB_PAGE_IDS:
            if pid in pages_in:
                pages[pid] = normalize_page(pages_in[pid], pid)
    for pid in KB_PAGE_IDS:
        if pid not in pages:
            pages[pid] = default_page(pid)
    version = raw.get("version")
    try:
        ver = int(version)
    except (TypeError, ValueError):
        ver = 1
    return {"version": ver, "pages": pages}


def kb_path(data_dir: Path) -> Path:
    return data_dir / "knowledge_base.json"


def load_document(data_dir: Path) -> dict[str, Any]:
    path = kb_path(data_dir)
    if not path.is_file():
        doc = default_document()
        save_document(data_dir, doc)
        return doc
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        doc = normalize_document(raw)
        return doc
    except Exception:
        return default_document()


def save_document(data_dir: Path, doc: dict[str, Any]) -> None:
    path = kb_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_document(doc)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_page(data_dir: Path, guide_id: str) -> dict[str, Any]:
    pid = str(guide_id or "").strip().lower()
    if pid not in KB_PAGE_IDS:
        raise ValueError(f"Unknown guide id: {guide_id}")
    doc = load_document(data_dir)
    return doc["pages"][pid]


def put_page(data_dir: Path, guide_id: str, page: dict[str, Any]) -> dict[str, Any]:
    pid = str(guide_id or "").strip().lower()
    if pid not in KB_PAGE_IDS:
        raise ValueError(f"Unknown guide id: {guide_id}")
    doc = load_document(data_dir)
    doc["pages"][pid] = normalize_page(page, pid)
    save_document(data_dir, doc)
    return doc["pages"][pid]


def list_pages_meta() -> list[dict[str, str]]:
    return [
        {
            "id": pid,
            "label": KB_PAGE_LABELS[pid],
            "group": KB_PAGE_GROUPS.get(pid, "main"),
        }
        for pid in KB_PAGE_IDS
    ]
