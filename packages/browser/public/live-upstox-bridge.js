(function () {
  const STATUS_URL = "/api/live/status";
  const SUBSCRIBE_URL = "/api/live/subscribe";
  const UNSUBSCRIBE_URL = "/api/live/unsubscribe";
  const MOVERS_START_URL = "/api/live/movers/start";
  const MOVERS_STOP_URL = "/api/live/movers/stop";
  const QUOTES_URL = "/api/live/quotes";
  const CANDLES_URL = "/api/live/candles/";
  const WS_URL = (window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host + "/ws/live";
  const RECONNECT_MS = 3000;

  let socket = null;
  let reconnectTimer = null;
  let wanted = {};
  const listeners = new Set();
  const liveState = window.CiMLiveState = window.CiMLiveState || {
    enabled: false,
    moversUniverse: false,
    contexts: {},
    lastSnapshot: null,
    quotes: {},
    candles: {}
  };
  if (typeof liveState.moversUniverse !== "boolean") liveState.moversUniverse = false;

  const storeListeners = new Set();
  const GLOBAL_REFRESH_EVENTS = [
    "nse-pulse-chart-data-updated",
    "cim-pnl-refresh",
    "dashboard-refresh",
    "cim-app-data-refresh",
    "cim-market-pulse-refresh",
    "cim-market-movers-refresh",
    "cim-market-map-refresh"
  ];

  function isLiveRefreshEvent(event) {
    const detail = event && event.detail;
    if (!detail || typeof detail !== "object") return false;
    if (detail.live === true) return true;
    if (String(detail.source || "").toLowerCase() === "upstox_stream") return true;
    if (detail.snapshot && detail.snapshot.status && String(detail.snapshot.status.source || "").toLowerCase() === "upstox_stream") return true;
    return false;
  }

  function installLiveRefreshGuard() {
    if (window.__cimLiveRefreshGuardInstalled) return;
    window.__cimLiveRefreshGuardInstalled = true;
    GLOBAL_REFRESH_EVENTS.forEach(function (name) {
      window.addEventListener(name, function (event) {
        if (!liveState.enabled || !isLiveRefreshEvent(event)) return;
        try { event.stopImmediatePropagation(); } catch (_) {}
      }, true);
    });
  }

  function mergeBag(target, bag) {
    if (!bag || typeof bag !== "object") return;
    Object.keys(bag).forEach(function (key) {
      const symbol = String(key || "").trim().toUpperCase();
      if (symbol) target[symbol] = bag[key];
    });
  }

  function applySnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") return;
    mergeBag(liveState.quotes, snapshot.quotes || snapshot.quote_map || snapshot.ltpc);
    mergeBag(liveState.candles, snapshot.candles || snapshot.candle_map || snapshot.ohlc);
  }

  function notifyStore(snapshot) {
    storeListeners.forEach(function (listener) {
      try { listener(snapshot, liveState); } catch (_) {}
    });
    emit("cim:live-store-updated", {
      snapshot: snapshot || null,
      quoteCount: Object.keys(liveState.quotes || {}).length,
      candleCount: Object.keys(liveState.candles || {}).length
    });
  }

  function appendLiveParams(url) {
    try {
      const u = new URL(String(url), window.location.origin);
      if (u.origin !== window.location.origin) return url;
      if (!/^\/api\/chart-data\//.test(u.pathname)) return url;
      if (!liveState.enabled) return url;
      if (!u.searchParams.has("live_today")) u.searchParams.set("live_today", "true");
      u.searchParams.set("_live_tick", String(Math.floor(Date.now() / 1000)));
      return u.pathname + u.search + u.hash;
    } catch (_) {
      return url;
    }
  }

  function patchNetwork() {
    if (window.__cimLiveNetworkPatched) return;
    window.__cimLiveNetworkPatched = true;
    const originalFetch = window.fetch;
    if (typeof originalFetch === "function") {
      window.fetch = function (input, init) {
        if (typeof input === "string") input = appendLiveParams(input);
        return originalFetch.call(this, input, init);
      };
    }
    const proto = window.XMLHttpRequest && window.XMLHttpRequest.prototype;
    if (proto && proto.open) {
      const originalOpen = proto.open;
      proto.open = function (method, url) {
        if (String(method || "GET").toUpperCase() === "GET" && typeof url === "string") {
          url = appendLiveParams(url);
        }
        const args = Array.prototype.slice.call(arguments);
        args[1] = url;
        return originalOpen.apply(this, args);
      };
    }
  }

  function emit(name, detail) {
    try {
      window.dispatchEvent(new CustomEvent(name, { detail }));
    } catch (_) {}
  }

  function notify(snapshot) {
    liveState.lastSnapshot = snapshot || null;
    applySnapshot(snapshot);
    listeners.forEach(function (listener) {
      try { listener(snapshot); } catch (_) {}
    });
    emit("cim:live-snapshot", snapshot);
    notifyStore(snapshot);
  }

  function api(path, options) {
    return fetch(path, Object.assign({
      cache: "no-store",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" }
    }, options || {})).then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    });
  }

  function apiWithTimeout(path, options, ms) {
    const timeoutMs = ms || 12000;
    const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = window.setTimeout(function () {
      try { if (ctrl) ctrl.abort(); } catch (_) {}
    }, timeoutMs);
    const opts = Object.assign({}, options || {});
    if (ctrl) opts.signal = ctrl.signal;
    return api(path, opts).finally(function () {
      window.clearTimeout(timer);
    });
  }

  function normalizeSymbols(symbols) {
    if (typeof symbols === "string") symbols = [symbols];
    if (!Array.isArray(symbols)) return [];
    return symbols.map(function (symbol) {
      return String(symbol || "").trim().toUpperCase();
    }).filter(Boolean);
  }

  function sendCurrentSubscriptions() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    Object.keys(wanted).forEach(function (context) {
      const sub = wanted[context];
      socket.send(JSON.stringify({
        action: "subscribe",
        context: context,
        symbols: sub.symbols,
        mode: sub.mode
      }));
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    if (!Object.keys(wanted).length && !liveState.moversUniverse) return;
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      if (Object.keys(wanted).length || liveState.moversUniverse) connect();
    }, RECONNECT_MS);
  }

  function disconnectSocket() {
    if (reconnectTimer) {
      try { window.clearTimeout(reconnectTimer); } catch (_) {}
      reconnectTimer = null;
    }
    const s = socket;
    socket = null;
    if (!s) return;
    try { s.onopen = null; s.onmessage = null; s.onerror = null; s.onclose = null; } catch (_) {}
    try { s.close(); } catch (_) {}
  }

  function clearLocalState() {
    wanted = {};
    liveState.enabled = false;
    liveState.moversUniverse = false;
    liveState.contexts = {};
    liveState.lastSnapshot = null;
    liveState.quotes = {};
    liveState.candles = {};
    disconnectSocket();
    notifyStore(null);
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
    try {
      socket = new WebSocket(WS_URL);
    } catch (_) {
      scheduleReconnect();
      return;
    }
    socket.onopen = function () {
      emit("cim:live-connected", { connected: true });
      sendCurrentSubscriptions();
    };
    socket.onmessage = function (event) {
      try { notify(JSON.parse(event.data)); } catch (_) {}
    };
    socket.onclose = function () {
      emit("cim:live-connected", { connected: false });
      scheduleReconnect();
    };
    socket.onerror = function () {
      emit("cim:live-connected", { connected: false });
    };
  }

  async function subscribe(context, symbols, mode) {
    context = String(context || "focus").trim() || "focus";
    mode = mode === "full" ? "full" : "ltpc";
    const clean = normalizeSymbols(symbols);
    wanted[context] = { symbols: clean, mode: mode };
    liveState.enabled = true;
    liveState.contexts[context] = { symbols: clean, mode: mode };
    const result = await apiWithTimeout(SUBSCRIBE_URL, {
      method: "POST",
      body: JSON.stringify({ context: context, symbols: clean, mode: mode })
    }, 15000);
    connect();
    sendCurrentSubscriptions();
    emit("cim:live-subscribe", result);
    return result;
  }

  async function unsubscribe(context) {
    context = String(context || "focus").trim() || "focus";
    delete wanted[context];
    delete liveState.contexts[context];
    liveState.enabled = Object.keys(liveState.contexts).length > 0 || !!liveState.moversUniverse;
    try {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "unsubscribe", context: context }));
      }
    } catch (_) {}
    try {
      const result = await apiWithTimeout(UNSUBSCRIBE_URL, {
        method: "POST",
        body: JSON.stringify({ context: context })
      }, 8000);
      emit("cim:live-unsubscribe", result);
      return result;
    } catch (err) {
      emit("cim:live-unsubscribe", { error: String(err && err.message || err) });
      return null;
    }
  }

  async function startMoversUniverse() {
    liveState.moversUniverse = true;
    liveState.enabled = true;
    const result = await apiWithTimeout(MOVERS_START_URL, {
      method: "POST",
      body: JSON.stringify({})
    }, 45000);
    emit("cim:live-movers-start", result);
    emit("cim:live-active", { enabled: true, movers: true });
    return result;
  }

  async function stopMoversUniverse() {
    liveState.moversUniverse = false;
    liveState.enabled = Object.keys(liveState.contexts).length > 0;
    try {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "movers_stop" }));
      }
    } catch (_) {}
    try {
      const result = await apiWithTimeout(MOVERS_STOP_URL, {
        method: "POST",
        body: JSON.stringify({})
      }, 8000);
      emit("cim:live-movers-stop", result);
      emit("cim:live-active", { enabled: liveState.enabled, movers: false });
      return result;
    } catch (err) {
      emit("cim:live-movers-stop", { error: String(err && err.message || err) });
      emit("cim:live-active", { enabled: liveState.enabled, movers: false });
      return null;
    }
  }

  async function stopAll() {
    // Local cut-over first so UI / patch overlay stop immediately even if the
    // backend is hung under a full-universe LTPC flood.
    const contexts = Object.keys(wanted);
    clearLocalState();
    emit("cim:live-active", { enabled: false, movers: false });
    emit("cim:live-feed-toggle", { enabled: false, movers: false });
    const jobs = contexts.map(function (ctx) {
      return apiWithTimeout(UNSUBSCRIBE_URL, {
        method: "POST",
        body: JSON.stringify({ context: ctx })
      }, 5000).catch(function () { return null; });
    });
    jobs.push(
      apiWithTimeout(MOVERS_STOP_URL, { method: "POST", body: JSON.stringify({}) }, 5000)
        .catch(function () { return null; })
    );
    await Promise.all(jobs);
    return { ok: true };
  }

  function status() {
    return api(STATUS_URL).then(function (data) {
      emit("cim:live-status", data);
      return data;
    });
  }

  function quotes(symbols) {
    const clean = normalizeSymbols(symbols);
    const query = clean.length ? "?symbols=" + encodeURIComponent(clean.join(",")) : "";
    return api(QUOTES_URL + query);
  }

  function candles(symbol) {
    return api(CANDLES_URL + encodeURIComponent(String(symbol || "").trim().toUpperCase()));
  }

  window.CiMLive = {
    subscribe: subscribe,
    unsubscribe: unsubscribe,
    startMoversUniverse: startMoversUniverse,
    stopMoversUniverse: stopMoversUniverse,
    stopAll: stopAll,
    clearLocalState: clearLocalState,
    status: status,
    quotes: quotes,
    candles: candles,
    connect: connect,
    onSnapshot: function (listener) {
      if (typeof listener !== "function") return function () {};
      listeners.add(listener);
      connect();
      return function () { listeners.delete(listener); };
    },
    onStoreUpdate: function (listener) {
      if (typeof listener !== "function") return function () {};
      storeListeners.add(listener);
      return function () { storeListeners.delete(listener); };
    },
    getState: function () {
      return liveState;
    },
    isActive: function () {
      return !!(liveState.enabled || liveState.moversUniverse);
    }
  };
  installLiveRefreshGuard();
  patchNetwork();
})();
