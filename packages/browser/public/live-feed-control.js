/**
 * Live Feed controller (headless) — page-bound ON/OFF + earnings-today state.
 * Scope follows the active App page (no Mode dropdown). UI: LiveFeedPopover.
 */
(function () {
  const STATE_KEY = "cim.liveFeedToggle.state.v1";
  const EARNINGS_TODAY_KEY = "cim.movers.earningsToday";
  const SOURCE_URL = "/api/movers/live/status";
  const LIVE_STATUS_URL = "/api/live/status";
  const SYMBOL_RE = /^[A-Z][A-Z0-9&.-]{1,19}$/;
  const INDEX_RE = /^\^[A-Z0-9]+$|^NIFTY_[A-Z0-9_.]+$/;
  const RESERVED = new Set(["LIVE", "OFF", "ON", "NSE", "BSE", "VIEW", "SAVE", "LAYOUT", "SEARCH", "INDEX", "VOLUME"]);

  const MODE_OPTIONS = [
    { value: "dashboard", label: "NSE", needsSymbol: false },
    { value: "indices", label: "Indices", needsSymbol: false },
    { value: "market-map", label: "Market Map", needsSymbol: false },
    { value: "market-pulse", label: "Market Pulse", needsSymbol: false },
    { value: "movers", label: "Market Movers", needsSymbol: false },
    { value: "watchlist", label: "Watchlist", needsSymbol: false },
    { value: "portfolio", label: "Portfolio", needsSymbol: false },
    { value: "pnl", label: "P&L", needsSymbol: false },
    { value: "focus", label: "Chart", needsSymbol: true }
  ];
  const PAGE_ID_FOR_MODE = {
    focus: "chart",
    dashboard: "dashboard",
    portfolio: "portfolio-dashboard",
    pnl: "pnl",
    indices: "indices",
    "market-map": "market-map",
    "market-pulse": "market-pulse",
    movers: "movers",
    watchlist: "watchlist",
    "potential-swings": "potential-swings",
    "earnings-beats": "earnings-beats",
    earnings: "earnings-beats"
  };
  const PAGE_FOCUS_CONTEXTS = new Set([
    "dashboard", "indices", "focus", "potential-swings"
  ]);

  function isListContext(ctx) {
    const c = String(ctx || "");
    return c === "dashboard"
      || c === "market-map"
      || c === "watchlist"
      || c === "market-pulse"
      || c === "portfolio"
      || c === "pnl"
      || c === "earnings-beats"
      || c === "earnings"
      || c.indexOf("constituents-") === 0;
  }

  function isFocusPageContext(ctx) {
    const c = String(ctx || "");
    return PAGE_FOCUS_CONTEXTS.has(c) || c.indexOf("index-") === 0;
  }

  function resolvePageId(ctx, pageId) {
    if (pageId) return String(pageId);
    return PAGE_ID_FOR_MODE[ctx] || ctx;
  }

  function contextLabelFor(ctx, pageLabel) {
    if (pageLabel) return String(pageLabel);
    const modeLabel = MODE_OPTIONS.find(function (o) { return o.value === ctx; });
    if (modeLabel) return modeLabel.label;
    if (String(ctx).indexOf("constituents-") === 0) {
      return "Constituents · " + String(ctx).slice("constituents-".length);
    }
    if (String(ctx).indexOf("index-") === 0) {
      return "Index · " + String(ctx).slice("index-".length);
    }
    return ctx || "this page";
  }

  let source = { label: "Upstox", detail: "" };
  let state = readState();
  let busy = false;
  let opGen = 0;
  let earningsToday = readEarningsToday();
  let suggestions = [];
  let suggestActive = -1;
  let suggestTimer = null;
  let suggestGen = 0;
  let focusSwitchTimer = null;
  let focusSwitchGen = 0;
  const listeners = new Set();

  function cleanSymbol(value) {
    const clean = String(value || "").trim().toUpperCase().replace(/\.NS$/, "");
    if (INDEX_RE.test(clean)) return clean;
    if (SYMBOL_RE.test(clean) && !RESERVED.has(clean)) return clean;
    return "";
  }

  function readState() {
    try {
      const raw = JSON.parse(localStorage.getItem(STATE_KEY) || "{}");
      let legacy = {};
      try { legacy = JSON.parse(localStorage.getItem("cim.liveFocusToggle.v1") || "{}"); } catch (_) {}
      let ctx = raw.context || "focus";
      if (ctx === "potential-swings") {
        ctx = "focus";
      }
      if (ctx === "earnings") ctx = "earnings-beats";
      return {
        enabled: false,
        context: ctx,
        pageId: raw.pageId || PAGE_ID_FOR_MODE[ctx] || ctx,
        pageLabel: raw.pageLabel || "",
        symbol: cleanSymbol(raw.symbol || legacy.symbol) || "",
        watchlist: raw.watchlist || "",
        detail: "Live feed off — open a page, then flip the switch",
        tone: "idle"
      };
    } catch (_) {
      return {
        enabled: false,
        context: "focus",
        pageId: "chart",
        pageLabel: "",
        symbol: "",
        watchlist: "",
        detail: "Live feed off — open a page, then flip the switch",
        tone: "idle"
      };
    }
  }

  function saveState() {
    try {
      localStorage.setItem(STATE_KEY, JSON.stringify({
        enabled: state.enabled,
        context: state.context,
        pageId: state.pageId,
        pageLabel: state.pageLabel,
        symbol: state.symbol,
        watchlist: state.watchlist
      }));
    } catch (_) {}
  }

  function readEarningsToday() {
    try {
      return localStorage.getItem(EARNINGS_TODAY_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function snapshot() {
    const label = contextLabelFor(state.context, state.pageLabel);
    return {
      enabled: !!state.enabled,
      busy: !!busy,
      context: state.context,
      pageId: state.pageId,
      contextLabel: label,
      symbol: state.symbol,
      watchlist: state.watchlist,
      detail: state.detail,
      tone: state.tone,
      source: { label: source.label, detail: source.detail },
      earningsToday: !!earningsToday,
      suggestions: suggestions.slice(),
      suggestActive: suggestActive,
      modes: MODE_OPTIONS.slice()
    };
  }

  function notify() {
    const snap = snapshot();
    listeners.forEach(function (fn) {
      try { fn(snap); } catch (_) {}
    });
  }

  function writeEarningsToday(on, fromExternal) {
    earningsToday = !!on;
    try {
      localStorage.setItem(EARNINGS_TODAY_KEY, earningsToday ? "1" : "0");
    } catch (_) {}
    if (!fromExternal) {
      try {
        window.dispatchEvent(new CustomEvent("cim:movers-earnings-today", {
          detail: { enabled: earningsToday }
        }));
      } catch (_) {}
    }
    notify();
  }

  function unique(list, limit) {
    const seen = new Set();
    const out = [];
    (list || []).forEach(function (item) {
      const s = cleanSymbol(item);
      if (s && !seen.has(s)) {
        seen.add(s);
        out.push(s);
      }
    });
    return out.slice(0, limit || 750);
  }

  function extract(value, out) {
    out = out || [];
    if (!value) return out;
    if (typeof value === "string") {
      const s = cleanSymbol(value);
      if (s) out.push(s);
      return out;
    }
    if (Array.isArray(value)) {
      value.forEach(function (item) { extract(item, out); });
      return out;
    }
    if (typeof value === "object") {
      ["symbol", "nse_symbol", "ticker"].forEach(function (key) {
        if (value[key]) extract(value[key], out);
      });
      ["items", "stocks", "positions", "holdings", "watchlists", "constituents", "data", "rows"].forEach(function (key) {
        if (value[key]) extract(value[key], out);
      });
    }
    return out;
  }

  function api(url) {
    return fetch(url, { cache: "no-store", credentials: "same-origin" }).then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    });
  }

  async function symbolsForMode() {
    const ctx = state.context;
    if (ctx === "movers") return [];
    if (ctx === "focus") return unique([state.symbol], 1);

    try {
      const pageApi = window.CiMPageSymbols;
      const pageId = resolvePageId(ctx, state.pageId);
      if (isListContext(ctx) && pageApi) {
        if (typeof pageApi.getSymbolsForPage === "function") {
          const pageSyms = unique(pageApi.getSymbolsForPage(pageId, state.symbol), 750);
          if (pageSyms.length) return pageSyms;
        }
        if (typeof pageApi.getRefreshSymbols === "function") {
          const focused = unique(pageApi.getRefreshSymbols(pageId, state.symbol), 750);
          if (focused.length) return focused;
        }
      }
      if (pageApi && typeof pageApi.getRefreshSymbols === "function") {
        const focused = unique(pageApi.getRefreshSymbols(pageId, state.symbol), 750);
        if (focused.length) return focused;
      }
      if (pageApi && typeof pageApi.getSymbolsForPage === "function") {
        const pageSyms = unique(pageApi.getSymbolsForPage(pageId, state.symbol), 750);
        if (pageSyms.length) return pageSyms;
      }
    } catch (_) {}

    if (ctx === "watchlist") {
      const data = await api("/api/watchlists");
      const lists = Array.isArray(data.watchlists) ? data.watchlists : [];
      const chosen = lists[0];
      return unique(extract(chosen || lists), 250);
    }
    if (ctx === "market-map" || String(ctx).indexOf("constituents-") === 0) return [];
    if (ctx === "market-pulse" || ctx === "indices") {
      try {
        const data = await api("/api/market-map/summary?period=1D");
        return unique(extract(data && (data.indices || data.data || data)), 100);
      } catch (_) {
        return unique([state.symbol], 1);
      }
    }
    const fallback = cleanSymbol(state.symbol);
    return fallback ? [fallback] : [];
  }

  function sourceSummary(moversData, liveData) {
    const data = moversData || {};
    const live = liveData || {};
    const upstoxOn = data.upstox_enabled !== false && live.configured !== false;
    const universeOn = !!(data.universe_subscribed || live.universe_subscribed);
    const universeN = data.universe_size || live.universe_size || data.quotes_fresh_count || 0;
    const counts = data.quote_source_counts || {};
    const streamN = Number(counts.upstox_stream || counts.upstox || 0);
    const src = String(data.quote_source || "").toLowerCase();

    if (!upstoxOn) {
      return { label: "Upstox off", detail: data.last_upstox_error || "token / kill switch" };
    }
    if (universeOn) {
      const conn = data.universe_connected || live.universe_connected ? "live" : "connecting";
      return { label: "Upstox", detail: (universeN ? universeN + " symbols · " : "") + conn };
    }
    if (data.fallback_active && streamN === 0 && src.indexOf("upstox") < 0) {
      return { label: "Upstox", detail: "fallback in use" };
    }
    if (state.enabled) {
      return { label: "Upstox", detail: "live" };
    }
    return { label: "Upstox", detail: "ready" };
  }

  async function pollSource() {
    try {
      const [moversRes, liveRes] = await Promise.all([
        fetch(SOURCE_URL, { credentials: "same-origin" }),
        fetch(LIVE_STATUS_URL, { credentials: "same-origin" }).catch(function () { return null; })
      ]);
      if (!moversRes.ok) throw new Error("status " + moversRes.status);
      const moversData = await moversRes.json();
      const liveData = liveRes && liveRes.ok ? await liveRes.json() : {};
      source = sourceSummary(moversData, liveData);
    } catch (_) {
      source = { label: "Upstox", detail: "status n/a" };
    }
    notify();
  }

  function scheduleSymbolSuggest(raw) {
    const q = String(raw || "").trim();
    if (suggestTimer) {
      try { clearTimeout(suggestTimer); } catch (_) {}
      suggestTimer = null;
    }
    if (q.length < 1) {
      suggestions = [];
      suggestActive = -1;
      notify();
      return;
    }
    const gen = ++suggestGen;
    suggestTimer = setTimeout(function () {
      suggestTimer = null;
      fetch("/api/unified-search?q=" + encodeURIComponent(q), {
        credentials: "same-origin",
        cache: "no-store"
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("search " + resp.status);
          return resp.json();
        })
        .then(function (data) {
          if (gen !== suggestGen) return;
          const stocks = Array.isArray(data.stocks) ? data.stocks : [];
          const indices = Array.isArray(data.indices) ? data.indices : [];
          const out = [];
          stocks.forEach(function (row) {
            const s = cleanSymbol(row && (row.symbol || row.Symbol || row));
            if (s) out.push(s);
          });
          indices.forEach(function (row) {
            const s = cleanSymbol(row && (row.symbol || row.Symbol || row));
            if (s) out.push(s);
          });
          if (!out.length && Array.isArray(data.results)) {
            data.results.forEach(function (row) {
              const s = cleanSymbol(row && (row.symbol || row.Symbol || row));
              if (s) out.push(s);
            });
          }
          suggestions = unique(out, 12);
          suggestActive = suggestions.length ? 0 : -1;
          notify();
        })
        .catch(function () {
          if (gen !== suggestGen) return;
          fetch("/api/stocks/search?q=" + encodeURIComponent(q), {
            credentials: "same-origin",
            cache: "no-store"
          })
            .then(function (resp) { return resp.ok ? resp.json() : { results: [] }; })
            .then(function (data) {
              if (gen !== suggestGen) return;
              suggestions = unique(data.results || [], 12);
              suggestActive = suggestions.length ? 0 : -1;
              notify();
            })
            .catch(function () {
              if (gen !== suggestGen) return;
              suggestions = [];
              suggestActive = -1;
              notify();
            });
        });
    }, 180);
  }

  function applyFocusedSymbol(raw, opts) {
    const openChart = !!(opts && opts.openChart);
    const s = cleanSymbol(raw);
    if (!s) return;
    state.symbol = s;
    suggestions = [];
    suggestActive = -1;
    saveState();
    notify();
    if (openChart) {
      window.dispatchEvent(new CustomEvent("cim:live-open-chart", {
        detail: { symbol: s }
      }));
    }
    if (state.enabled && state.context === "focus") sync();
    else if (!state.enabled && state.context === "focus") {
      state.detail = "Focused " + s + " — flip LIVE on for ticks";
      notify();
    }
  }

  async function clearOtherPageContexts(keep) {
    if (!window.CiMLive) return;
    const liveState = (window.CiMLive.getState && window.CiMLive.getState()) || window.CiMLiveState || {};
    const active = Object.keys((liveState && liveState.contexts) || {});
    const known = MODE_OPTIONS.map(function (o) { return o.value; });
    const all = {};
    active.forEach(function (c) { all[c] = true; });
    known.forEach(function (c) { all[c] = true; });
    // Always clear dynamic page contexts (constituents-*, index-*) too.
    Object.keys(all).forEach(function (c) { /* noop ensure enum */ });
    for (const ctx of Object.keys(all)) {
      if (ctx === keep) continue;
      // Movers mode keeps a parallel focus chart subscription.
      if (keep === "movers" && ctx === "focus") continue;
      // Keep focus socket alive across page resubscribes; ensureFocusSymbol retargets it.
      if (keep !== "movers" && ctx === "focus") continue;
      // Basket is a floating tray — BasketProvider owns subscribe/unsubscribe.
      if (ctx === "basket") continue;
      try { await window.CiMLive.unsubscribe(ctx); } catch (_) {}
    }
    // Also drop any leftover dynamic contexts not in the known set.
    for (const ctx of active) {
      if (ctx === keep) continue;
      if (ctx === "focus") continue;
      if (ctx === "basket") continue;
      if (all[ctx]) continue;
      try { await window.CiMLive.unsubscribe(ctx); } catch (_) {}
    }
    if (keep !== "movers") {
      try { await window.CiMLive.stopMoversUniverse(); } catch (_) {}
    }
  }

  async function ensureFocusSymbol(symbol) {
    const s = cleanSymbol(symbol);
    if (!s || !window.CiMLive) return null;
    state.symbol = s;
    saveState();
    // Chart candles + continuous LTP require focus/full (server forces full for focus).
    await window.CiMLive.subscribe("focus", [s], "full");
    return s;
  }

  function queueContextFocusSymbol(symbol) {
    const s = cleanSymbol(symbol);
    if (!s) return;
    state.symbol = s;
    saveState();
    notify();
    const gen = ++focusSwitchGen;
    if (focusSwitchTimer) {
      try { clearTimeout(focusSwitchTimer); } catch (_) {}
      focusSwitchTimer = null;
    }
    focusSwitchTimer = setTimeout(function () {
      focusSwitchTimer = null;
      if (gen !== focusSwitchGen) return;
      if (!state.enabled) return;

      // Always keep continuous focus/full ticks for the charted symbol.
      ensureFocusSymbol(s).then(function (focusSym) {
        if (!focusSym || gen !== focusSwitchGen) return;
        if (state.context === "movers") {
          state.detail = "LIVE ON — Market movers + chart focus " + focusSym;
          notify();
          window.dispatchEvent(new CustomEvent("cim:live-feed-toggle", {
            detail: {
              enabled: true,
              context: "movers",
              pageId: state.pageId || "movers",
              symbols: [focusSym],
              mode: "ltpc",
              movers: true
            }
          }));
          return;
        }
        if (isListContext(state.context)) {
          // List subscription stays as-is; only chart focus retargets.
          const name = contextLabelFor(state.context, state.pageLabel);
          state.detail = "LIVE ON — " + name + " + chart focus " + focusSym;
          notify();
          window.dispatchEvent(new CustomEvent("cim:live-feed-toggle", {
            detail: {
              enabled: true,
              context: state.context,
              pageId: state.pageId || state.context,
              symbols: [focusSym],
              mode: "full",
              movers: false
            }
          }));
          return;
        }
        // Page focus contexts (NSE / indices / chart): retarget page LTPC + focus/full.
        const subContext = state.context === "focus" ? "focus" : state.context;
        const pageSub = subContext === "focus"
          ? Promise.resolve()
          : window.CiMLive.subscribe(subContext, [s], "ltpc");
        pageSub.then(function () {
          if (gen !== focusSwitchGen) return;
          const name = contextLabelFor(state.context, state.pageLabel);
          state.detail = "LIVE ON — " + name + " — " + s;
          notify();
          window.dispatchEvent(new CustomEvent("cim:live-feed-toggle", {
            detail: {
              enabled: true,
              context: subContext,
              pageId: state.pageId || subContext,
              symbols: [s],
              mode: "full",
              movers: false
            }
          }));
        }).catch(function () {});
      }).catch(function () {});
    }, 120);
  }

  async function sync() {
    if (!window.CiMLive) {
      state.enabled = false;
      state.tone = "err";
      state.detail = "Live bridge not loaded. Hard refresh the page.";
      notify();
      return;
    }
    const gen = ++opGen;
    busy = true;
    state.enabled = true;
    state.tone = "idle";
    state.detail = "Starting live feed (" + state.context + ")…";
    saveState();
    notify();
    try {
      await window.CiMLive.connect();
      if (gen !== opGen) return;
      await clearOtherPageContexts(state.context);
      if (gen !== opGen) return;

      if (state.context === "movers") {
        await window.CiMLive.startMoversUniverse();
        if (gen !== opGen) return;
        const focusSym = await ensureFocusSymbol(state.symbol);
        if (gen !== opGen) return;
        state.tone = "ok";
        state.detail = focusSym
          ? ("LIVE ON — Market movers + chart focus " + focusSym)
          : "LIVE ON — Market movers (select a symbol for chart focus)";
        window.dispatchEvent(new CustomEvent("cim:live-feed-toggle", {
          detail: {
            enabled: true,
            context: "movers",
            pageId: state.pageId || "movers",
            symbols: focusSym ? [focusSym] : [],
            mode: "ltpc",
            movers: true
          }
        }));
        window.dispatchEvent(new CustomEvent("cim:live-active", {
          detail: {
            enabled: true,
            movers: true,
            context: "movers",
            pageId: state.pageId || "movers",
            focusSymbol: focusSym || null
          }
        }));
      } else {
        const symbols = await symbolsForMode();
        if (gen !== opGen) return;
        if (!symbols.length) {
          const pageName = contextLabelFor(state.context, state.pageLabel);
          throw new Error(
            state.context === "focus"
              ? "Select a chart symbol first"
              : state.context === "market-map"
                ? "Select an index on the Market Map left list first"
                : state.context === "watchlist"
                  ? "Open a watchlist on the Watchlist page first"
                  : state.context === "earnings-beats" || state.context === "earnings"
                    ? "Wait for Earnings rows to load first"
                  : String(state.context).indexOf("constituents-") === 0
                    ? "Wait for constituents to load on " + pageName
                    : "Select a symbol on " + pageName + " first"
          );
        }
        const mode = state.context === "focus" ? "full" : "ltpc";
        const subContext = state.context === "focus" ? "focus" : state.context;
        await window.CiMLive.subscribe(subContext, symbols, mode);
        if (gen !== opGen) return;
        // Keep continuous focus/full ticks for the charted symbol (candles + LTP).
        const focusSym = cleanSymbol(state.symbol) || (symbols.length ? symbols[0] : "");
        if (focusSym && subContext !== "focus") {
          await ensureFocusSymbol(focusSym);
          if (gen !== opGen) return;
        }
        state.tone = "ok";
        const pageName = contextLabelFor(state.context, state.pageLabel);
        if (symbols.length === 1 && isFocusPageContext(state.context)) {
          state.detail = "LIVE ON — " + pageName + " — " + symbols[0];
        } else {
          state.detail =
            "LIVE ON — " + pageName + " — " + symbols.length +
            " symbol" + (symbols.length === 1 ? "" : "s") + " (" + mode.toUpperCase() + ")" +
            (focusSym && subContext !== "focus" ? (" · chart " + focusSym) : "");
        }
        window.dispatchEvent(new CustomEvent("cim:live-feed-toggle", {
          detail: {
            enabled: true,
            context: subContext,
            pageId: state.pageId || resolvePageId(state.context, state.pageId),
            symbols: symbols,
            mode: mode,
            movers: false,
            focusSymbol: focusSym || null
          }
        }));
        window.dispatchEvent(new CustomEvent("cim:live-active", {
          detail: {
            enabled: true,
            movers: false,
            context: subContext,
            pageId: state.pageId || resolvePageId(state.context, state.pageId)
          }
        }));
      }
    } catch (err) {
      if (gen !== opGen) return;
      state.enabled = false;
      state.tone = "err";
      state.detail = "Live failed: " + (err && err.message ? err.message : String(err));
      try {
        if (window.CiMLive && typeof window.CiMLive.stopAll === "function") {
          await window.CiMLive.stopAll();
        }
      } catch (_) {}
      window.dispatchEvent(new CustomEvent("cim:live-active", {
        detail: { enabled: false, movers: false }
      }));
    }
    if (gen === opGen) {
      busy = false;
      saveState();
      notify();
      pollSource();
    }
  }

  async function stop() {
    const gen = ++opGen;
    busy = true;
    const context = state.context || "focus";
    state.enabled = false;
    state.tone = "idle";
    state.detail = "Stopping live feed…";
    saveState();
    notify();
    try {
      if (window.CiMLive && typeof window.CiMLive.stopAll === "function") {
        await window.CiMLive.stopAll();
      } else if (window.CiMLive) {
        try { await window.CiMLive.clearLocalState && window.CiMLive.clearLocalState(); } catch (_) {}
        try { await clearOtherPageContexts(null); } catch (_) {}
        try { await window.CiMLive.unsubscribe(context); } catch (_) {}
        try { await window.CiMLive.stopMoversUniverse(); } catch (_) {}
      }
    } catch (_) {}
    if (gen !== opGen) return;
    state.detail = "Live feed off — open a page, then flip the switch";
    window.dispatchEvent(new CustomEvent("cim:live-feed-toggle", {
      detail: {
        enabled: false,
        context: context,
        pageId: state.pageId || resolvePageId(context, state.pageId),
        movers: false
      }
    }));
    window.dispatchEvent(new CustomEvent("cim:live-active", {
      detail: {
        enabled: false,
        movers: false,
        context: context,
        pageId: state.pageId || resolvePageId(context, state.pageId)
      }
    }));
    busy = false;
    notify();
    pollSource();
  }

  function toggle() {
    if (busy || state.enabled) {
      stop();
      return;
    }
    sync();
  }

  function setContext(next) {
    const ctx = String(next || "focus");
    state.context = ctx;
    state.pageId = PAGE_ID_FOR_MODE[ctx] || ctx;
    state.pageLabel = contextLabelFor(ctx, "");
    suggestions = [];
    suggestActive = -1;
    saveState();
    notify();
    if (state.enabled) sync();
  }

  /** Bind Live scope to the active App page (replaces Mode dropdown). */
  function setPageContext(info) {
    const payload = info || {};
    const ctx = String(payload.context || "focus");
    const pageId = String(payload.pageId || PAGE_ID_FOR_MODE[ctx] || ctx);
    const label = String(payload.label || "");
    const nextSym = cleanSymbol(payload.symbol);
    const pageChanged = state.context !== ctx || state.pageId !== pageId;
    const symbolChanged = !!(nextSym && state.symbol !== nextSym);
    const labelChanged = !!(label && state.pageLabel !== label);
    state.context = ctx;
    state.pageId = pageId;
    if (label) state.pageLabel = label;
    if (nextSym) state.symbol = nextSym;
    suggestions = [];
    suggestActive = -1;
    saveState();
    if (!state.enabled) {
      state.detail = "Live feed off — scope: " + contextLabelFor(ctx, state.pageLabel);
      notify();
      return;
    }
    // Page change → full resubscribe. Symbol-only change → retarget focus (no stream tear-down).
    if (pageChanged) sync();
    else if (symbolChanged) queueContextFocusSymbol(nextSym);
    else if (labelChanged) notify();
    else notify();
  }

  function setSymbolDraft(raw) {
    if (state.context !== "focus") return;
    const text = String(raw || "");
    state.symbol = cleanSymbol(text) || text.trim().toUpperCase();
    saveState();
    scheduleSymbolSuggest(text);
    notify();
  }

  function setSuggestActive(idx) {
    if (!suggestions.length) return;
    suggestActive = Math.max(0, Math.min(suggestions.length - 1, idx));
    notify();
  }

  function clearSuggestions() {
    suggestions = [];
    suggestActive = -1;
    notify();
  }

  // Remove any leftover floating panel from older bundles.
  function scrubLegacyDom() {
    ["cim-live-feed-control", "cim-live-feed-toggle", "cim-live-feed-control-style"].forEach(function (id) {
      const el = document.getElementById(id);
      if (el && el.parentNode) el.parentNode.removeChild(el);
    });
  }

  window.addEventListener("cim-global-search-select", function (event) {
    const s = cleanSymbol(event && event.detail && event.detail.symbol);
    if (s) {
      state.symbol = s;
      saveState();
      notify();
      if (state.enabled && state.context === "focus") sync();
    }
  });
  window.addEventListener("cim:movers-earnings-today", function (event) {
    const next = !!(event && event.detail && event.detail.enabled);
    if (next === earningsToday) return;
    writeEarningsToday(next, true);
  });
  window.addEventListener("cim:watchlist-active", function (event) {
    const name = String(event && event.detail && event.detail.name || "").trim();
    if (!name) return;
    state.watchlist = name;
    saveState();
    if (state.enabled && state.context === "watchlist") sync();
  });
  window.addEventListener("cim:chart-focus-symbol", function (event) {
    const s = cleanSymbol(event && event.detail && (event.detail.symbol || event.detail));
    if (!s) return;
    state.symbol = s;
    saveState();
    notify();
    if (!state.enabled) return;
    if (state.context === "focus") {
      sync();
      return;
    }
    if (
      state.context === "movers"
      || isFocusPageContext(state.context)
      || isListContext(state.context)
    ) {
      queueContextFocusSymbol(s);
    }
  });

  window.addEventListener("cim:live-page-context", function (event) {
    const detail = (event && event.detail) || {};
    setPageContext(detail);
  });

  window.addEventListener("cim:page-symbols-changed", function (event) {
    const pageId = String(event && event.detail && event.detail.pageId || "").trim();
    if (!state.enabled || !pageId) return;
    if (pageId !== String(state.pageId || "").trim()) return;
    if (!isListContext(state.context) && state.context !== "market-pulse") return;
    sync();
  });

  window.CiMLiveFeedControl = {
    getSnapshot: snapshot,
    subscribe: function (fn) {
      if (typeof fn !== "function") return function () {};
      listeners.add(fn);
      try { fn(snapshot()); } catch (_) {}
      return function () { listeners.delete(fn); };
    },
    toggle: toggle,
    start: sync,
    stop: stop,
    setContext: setContext,
    setPageContext: setPageContext,
    setSymbolDraft: setSymbolDraft,
    applyFocusedSymbol: applyFocusedSymbol,
    setEarningsToday: function (on) { writeEarningsToday(!!on, false); },
    setSuggestActive: setSuggestActive,
    clearSuggestions: clearSuggestions,
    MODE_OPTIONS: MODE_OPTIONS
  };

  function boot() {
    scrubLegacyDom();
    notify();
    pollSource();
    window.setInterval(pollSource, 15000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
