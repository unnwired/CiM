import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import api from '../api/http';
import { searchUniverse } from '../api/client';
import { typingFieldKeyProps } from '../utils/isTypingTarget';
import { CimDialogButton, CimFormDialog, CIM_DIALOG_WIDTH_WIDE } from './cimDialogChrome';

const GEOM_KEY = 'cim.universalAlerts.geom.v1';
const PANEL_MIN = { w: 560, h: 320 };
const Z_PANEL = 300000;
const Z_TG_HELP = Z_PANEL + 100;

const btnSm = {
  fontSize: 11, padding: '2px 8px', borderRadius: 4, cursor: 'pointer',
  border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
  flexShrink: 0,
};
const inputFixed = {
  fontSize: 11, padding: '3px 6px', borderRadius: 4, boxSizing: 'border-box',
  border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
  flex: '0 0 auto',
};
const pctInputStyle = {
  width: 52, fontSize: 11, padding: '2px 4px', borderRadius: 4, boxSizing: 'border-box',
  border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
};

function loadGeometry() {
  try {
    const raw = localStorage.getItem(GEOM_KEY);
    if (raw) {
      const g = JSON.parse(raw);
      if (g && typeof g.w === 'number' && typeof g.h === 'number'
        && typeof g.left === 'number' && typeof g.top === 'number') {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        return {
          w: Math.max(PANEL_MIN.w, Math.min(g.w, vw - 24)),
          h: Math.max(PANEL_MIN.h, Math.min(g.h, vh - 24)),
          left: Math.max(0, Math.min(g.left, vw - 80)),
          top: Math.max(0, Math.min(g.top, vh - 60)),
        };
      }
    }
  } catch (_) {}
  return { w: 400, h: 360, left: Math.max(12, window.innerWidth - 440), top: 64 };
}

function saveGeometry(geom) {
  try { localStorage.setItem(GEOM_KEY, JSON.stringify(geom)); } catch (_) {}
}

function formatWhen(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
    return d.toLocaleString('en-IN', { hour12: false });
  } catch {
    return String(iso).slice(0, 16);
  }
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/** @returns {{ year: number, month: number } | null} month is 1–12 */
function alertYearMonth(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  } catch {
    return null;
  }
}

function monthKey(y, m) {
  return `${y}-${String(m).padStart(2, '0')}`;
}

function buildMonthOptions(alerts) {
  const keys = new Set();
  for (const a of alerts || []) {
    const ym = alertYearMonth(a?.created_at);
    if (ym) keys.add(monthKey(ym.year, ym.month));
  }
  const now = new Date();
  keys.add(monthKey(now.getFullYear(), now.getMonth() + 1));
  return Array.from(keys).sort().reverse().map((k) => {
    const [ys, ms] = k.split('-');
    const year = Number(ys);
    const month = Number(ms);
    return { key: k, year, month, label: `${MONTH_NAMES[month - 1]} ${year}` };
  });
}

async function maybeBrowserNotify(alerts, browserEnabled) {
  if (!browserEnabled || typeof window === 'undefined' || !('Notification' in window)) return;
  if (Notification.permission === 'default') {
    try { await Notification.requestPermission(); } catch (_) { return; }
  }
  if (Notification.permission !== 'granted') return;
  for (const a of alerts.slice(0, 5)) {
    try {
      // eslint-disable-next-line no-new
      new Notification(a.title || a.symbol || 'CiM Alert', {
        body: a.body || '',
        tag: a.id || a.dedup_key,
      });
    } catch (_) { /* ignore */ }
  }
}

export default function UniversalAlerts({ onOpenChart }) {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [unread, setUnread] = useState(0);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [monthFilter, setMonthFilter] = useState('all');
  const [dayMoveDraft, setDayMoveDraft] = useState('');
  const [portfolioMoveDraft, setPortfolioMoveDraft] = useState('');
  const [ptSymbol, setPtSymbol] = useState('');
  const [ptDirection, setPtDirection] = useState('above');
  const [ptLevel, setPtLevel] = useState('');
  const [ptSuggestions, setPtSuggestions] = useState([]);
  const [ptSuggestOpen, setPtSuggestOpen] = useState(false);
  const [ptActiveIdx, setPtActiveIdx] = useState(-1);
  const [ptListOpen, setPtListOpen] = useState(false);
  const ptSuggestTimerRef = useRef(null);
  const ptSymbolWrapRef = useRef(null);
  const ptListWrapRef = useRef(null);
  const [tgTokenDraft, setTgTokenDraft] = useState('');
  const [tgChatDraft, setTgChatDraft] = useState('');
  const [tgHelpOpen, setTgHelpOpen] = useState(false);
  const [geom, setGeom] = useState(() => (typeof window !== 'undefined' ? loadGeometry() : { w: 400, h: 360, left: 40, top: 64 }));
  const panelRef = useRef(null);
  const dragRef = useRef({ active: false, sx: 0, sy: 0, sl: 0, st: 0 });
  const resizeRef = useRef({ active: false, sx: 0, sy: 0, sw: 0, sh: 0 });
  const seenPendingRef = useRef(new Set());

  const openAlertSymbol = useCallback((rawSymbol) => {
    const sym = String(rawSymbol || '').trim().toUpperCase();
    if (!sym || typeof onOpenChart !== 'function') return;
    onOpenChart(sym);
    setOpen(false);
  }, [onOpenChart]);

  const loadAlerts = useCallback(async ({ notify = false } = {}) => {
    try {
      const [aRes, sRes] = await Promise.all([
        api.get('/api/user-alerts'),
        api.get('/api/alert-settings'),
      ]);
      const nextAlerts = Array.isArray(aRes.data?.alerts) ? aRes.data.alerts : [];
      setAlerts(nextAlerts);
      setUnread(Number(aRes.data?.unread) || 0);
      setSettings(sRes.data || null);
      if (sRes.data) {
        const dm = Number(sRes.data.day_move_pct);
        const pm = Number(sRes.data.portfolio_day_move_pct);
        setDayMoveDraft(Number.isFinite(dm) ? String(dm) : '3');
        setPortfolioMoveDraft(Number.isFinite(pm) ? String(pm) : '3');
      }
      const pending = Array.isArray(aRes.data?.browser_pending) ? aRes.data.browser_pending : [];
      if (notify && pending.length && sRes.data?.browser_enabled) {
        const fresh = pending.filter((p) => p?.id && !seenPendingRef.current.has(p.id));
        if (fresh.length) {
          fresh.forEach((p) => seenPendingRef.current.add(p.id));
          await maybeBrowserNotify(fresh, true);
          await api.put('/api/user-alerts', {
            ids: fresh.map((p) => p.id),
            clear_browser_pending: true,
          });
        }
      }
    } catch (_) { /* ignore */ }
  }, []);

  useEffect(() => {
    loadAlerts({ notify: true });
    const t = setInterval(() => loadAlerts({ notify: true }), 30000);
    return () => clearInterval(t);
  }, [loadAlerts]);

  useEffect(() => {
    function onMove(e) {
      if (dragRef.current.active) {
        const d = dragRef.current;
        const left = Math.max(0, Math.min(window.innerWidth - 80, d.sl + (e.clientX - d.sx)));
        const top = Math.max(0, Math.min(window.innerHeight - 60, d.st + (e.clientY - d.sy)));
        setGeom((g) => ({ ...g, left, top }));
      }
      if (resizeRef.current.active) {
        const r = resizeRef.current;
        const w = Math.max(PANEL_MIN.w, Math.min(window.innerWidth - 24, r.sw + (e.clientX - r.sx)));
        const h = Math.max(PANEL_MIN.h, Math.min(window.innerHeight - 24, r.sh + (e.clientY - r.sy)));
        setGeom((g) => ({ ...g, w, h }));
      }
    }
    function onUp() {
      if (dragRef.current.active || resizeRef.current.active) {
        dragRef.current.active = false;
        resizeRef.current.active = false;
        setGeom((g) => {
          saveGeometry(g);
          return g;
        });
      }
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const toggleOpen = useCallback(() => {
    setOpen((prev) => {
      if (!prev) loadAlerts({ notify: true });
      return !prev;
    });
  }, [loadAlerts]);

  const startDrag = useCallback((e) => {
    if (e.button !== 0) return;
    dragRef.current = { active: true, sx: e.clientX, sy: e.clientY, sl: geom.left, st: geom.top };
    e.preventDefault();
  }, [geom.left, geom.top]);

  const startResize = useCallback((e) => {
    if (e.button !== 0) return;
    resizeRef.current = { active: true, sx: e.clientX, sy: e.clientY, sw: geom.w, sh: geom.h };
    e.preventDefault();
    e.stopPropagation();
  }, [geom.w, geom.h]);

  async function patchSettings(patch) {
    setBusy(true);
    setStatusMsg('');
    try {
      const r = await api.put('/api/alert-settings', patch);
      setSettings(r.data);
      const dm = Number(r.data?.day_move_pct);
      const pm = Number(r.data?.portfolio_day_move_pct);
      if (Number.isFinite(dm)) setDayMoveDraft(String(dm));
      if (Number.isFinite(pm)) setPortfolioMoveDraft(String(pm));
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Failed to save settings');
    } finally {
      setBusy(false);
    }
  }

  function commitPctDraft(kind) {
    const raw = kind === 'portfolio' ? portfolioMoveDraft : dayMoveDraft;
    const v = Number(raw);
    if (!Number.isFinite(v)) {
      if (kind === 'portfolio') setPortfolioMoveDraft(String(settings?.portfolio_day_move_pct ?? 3));
      else setDayMoveDraft(String(settings?.day_move_pct ?? 3));
      return;
    }
    if (kind === 'portfolio') patchSettings({ portfolio_day_move_pct: v });
    else patchSettings({ day_move_pct: v });
  }

  const pctKeyProps = typingFieldKeyProps();

  async function markAllRead() {
    try {
      const r = await api.put('/api/user-alerts', { mark_all_read: true, clear_browser_pending: true });
      setAlerts(r.data?.alerts || []);
      setUnread(r.data?.unread || 0);
    } catch (_) { /* ignore */ }
  }

  async function markOneRead(id) {
    try {
      const r = await api.put('/api/user-alerts', { ids: [id], clear_browser_pending: true });
      setAlerts(r.data?.alerts || []);
      setUnread(r.data?.unread || 0);
    } catch (_) { /* ignore */ }
  }

  async function deleteOne(id) {
    if (!id) return;
    try {
      const r = await api.put('/api/user-alerts', { delete_ids: [id] });
      setAlerts(r.data?.alerts || []);
      setUnread(r.data?.unread || 0);
    } catch (_) { /* ignore */ }
  }

  async function clearAll() {
    if (!window.confirm('Delete all alerts from the inbox? This cannot be undone.')) return;
    try {
      const r = await api.put('/api/user-alerts', { clear_all: true });
      setAlerts(r.data?.alerts || []);
      setUnread(r.data?.unread || 0);
    } catch (_) { /* ignore */ }
  }

  async function addPriceTarget() {
    const symbol = String(ptSymbol || '').trim().toUpperCase();
    const level = Number(ptLevel);
    if (!symbol || !Number.isFinite(level) || level <= 0) {
      setStatusMsg('Enter a symbol and a price level > 0');
      return;
    }
    setBusy(true);
    setStatusMsg('');
    try {
      const r = await api.post('/api/price-targets', {
        symbol,
        direction: ptDirection === 'below' ? 'below' : 'above',
        level,
      });
      setSettings((prev) => ({ ...(prev || {}), price_targets: r.data?.price_targets || [] }));
      setPtSymbol('');
      setPtLevel('');
      setStatusMsg(`Armed ${symbol} ${ptDirection === 'below' ? '≤' : '≥'} ₹${level}`);
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Failed to save price target');
    } finally {
      setBusy(false);
    }
  }

  async function rearmPriceTarget(id) {
    setBusy(true);
    try {
      const r = await api.put(`/api/price-targets/${encodeURIComponent(id)}/armed`, { armed: true });
      setSettings((prev) => ({ ...(prev || {}), price_targets: r.data?.price_targets || [] }));
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Failed to re-arm');
    } finally {
      setBusy(false);
    }
  }

  async function deletePriceTarget(id) {
    setBusy(true);
    try {
      const r = await api.delete(`/api/price-targets/${encodeURIComponent(id)}`);
      setSettings((prev) => ({ ...(prev || {}), price_targets: r.data?.price_targets || [] }));
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Failed to delete');
    } finally {
      setBusy(false);
    }
  }

  const priceTargets = Array.isArray(settings?.price_targets) ? settings.price_targets : [];
  const armedTargetCount = priceTargets.filter((t) => t?.armed).length;
  const sortedPriceTargets = [...priceTargets].sort((a, b) => {
    const armedDelta = Number(Boolean(b?.armed)) - Number(Boolean(a?.armed));
    if (armedDelta !== 0) return armedDelta;
    const sym = String(a?.symbol || '').localeCompare(String(b?.symbol || ''));
    if (sym !== 0) return sym;
    return Number(a?.level || 0) - Number(b?.level || 0);
  });

  useEffect(() => {
    if (ptSuggestTimerRef.current) clearTimeout(ptSuggestTimerRef.current);
    const q = String(ptSymbol || '').trim();
    if (q.length < 1) {
      setPtSuggestions([]);
      setPtSuggestOpen(false);
      setPtActiveIdx(-1);
      return undefined;
    }
    ptSuggestTimerRef.current = setTimeout(async () => {
      try {
        const d = await searchUniverse(q);
        const stocks = (d.stocks || []).map((s) => {
          if (typeof s === 'string') return String(s).toUpperCase();
          return String(s?.Symbol || s?.symbol || '').toUpperCase();
        }).filter(Boolean);
        const uniq = [...new Set(stocks)].slice(0, 12);
        setPtSuggestions(uniq);
        setPtSuggestOpen(uniq.length > 0);
        setPtActiveIdx(uniq.length ? 0 : -1);
      } catch {
        setPtSuggestions([]);
        setPtSuggestOpen(false);
        setPtActiveIdx(-1);
      }
    }, 200);
    return () => {
      if (ptSuggestTimerRef.current) clearTimeout(ptSuggestTimerRef.current);
    };
  }, [ptSymbol]);

  useEffect(() => {
    function onDocDown(e) {
      if (ptSymbolWrapRef.current && !ptSymbolWrapRef.current.contains(e.target)) {
        setPtSuggestOpen(false);
      }
      if (ptListWrapRef.current && !ptListWrapRef.current.contains(e.target)) {
        setPtListOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, []);

  function pickPtSymbol(sym) {
    const s = String(sym || '').trim().toUpperCase();
    if (!s) return;
    setPtSymbol(s);
    setPtSuggestions([]);
    setPtSuggestOpen(false);
    setPtActiveIdx(-1);
  }

  function onPtSymbolKeyDown(e) {
    e.stopPropagation();
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!ptSuggestions.length) return;
      setPtSuggestOpen(true);
      setPtActiveIdx((i) => Math.min((i < 0 ? -1 : i) + 1, ptSuggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setPtActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (ptSuggestOpen && ptActiveIdx >= 0 && ptSuggestions[ptActiveIdx]) {
        e.preventDefault();
        pickPtSymbol(ptSuggestions[ptActiveIdx]);
      }
    } else if (e.key === 'Escape') {
      setPtSuggestOpen(false);
    }
  }

  async function sendTelegramTest() {
    setBusy(true);
    setStatusMsg('');
    try {
      const r = await api.post('/api/alert-settings/telegram-test');
      if (r.data?.ok) {
        setStatusMsg('Telegram test sent — check your phone.');
        loadAlerts();
      } else {
        setStatusMsg(r.data?.error || 'Telegram test failed');
      }
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Telegram test failed');
    } finally {
      setBusy(false);
    }
  }

  async function saveTelegramCredentials() {
    const token = String(tgTokenDraft || '').trim();
    const chat = String(tgChatDraft || '').trim();
    if (!token || !chat) {
      setStatusMsg('Enter your bot token and chat ID, then Save.');
      return;
    }
    setBusy(true);
    setStatusMsg('');
    try {
      const r = await api.put('/api/alert-settings/telegram', {
        bot_token: token,
        chat_id: chat,
      });
      setSettings((prev) => ({ ...(prev || {}), telegram: r.data?.telegram || prev?.telegram }));
      setTgTokenDraft('');
      setTgChatDraft('');
      const uname = r.data?.telegram?.bot_username;
      setStatusMsg(uname
        ? `Connected to ${uname} (encrypted on server).`
        : 'Telegram credentials saved — Connected.');
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Could not save Telegram credentials');
    } finally {
      setBusy(false);
    }
  }

  async function clearTelegramCredentials() {
    if (!window.confirm('Remove your saved Telegram bot token and chat ID from this account?')) return;
    setBusy(true);
    setStatusMsg('');
    try {
      const r = await api.delete('/api/alert-settings/telegram');
      setSettings((prev) => ({ ...(prev || {}), telegram: r.data?.telegram || prev?.telegram }));
      setTgTokenDraft('');
      setTgChatDraft('');
      setStatusMsg('Telegram credentials cleared.');
    } catch (e) {
      setStatusMsg(e.response?.data?.detail || e.message || 'Could not clear Telegram credentials');
    } finally {
      setBusy(false);
    }
  }

  async function enableBrowserNotifications() {
    if (!('Notification' in window)) {
      setStatusMsg('This browser does not support notifications.');
      return;
    }
    try {
      const perm = await Notification.requestPermission();
      if (perm === 'granted') {
        // eslint-disable-next-line no-new
        new Notification('CiM alerts enabled', { body: 'Browser notifications are on.' });
        await patchSettings({ browser_enabled: true });
        setStatusMsg('Browser notifications allowed.');
      } else {
        setStatusMsg('Browser notification permission denied.');
      }
    } catch (e) {
      setStatusMsg(e.message || 'Could not request permission');
    }
  }

  const btn = (
    <div
      onClick={toggleOpen}
      title={open ? 'Hide alerts' : 'Show alerts inbox'}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        padding: '0 12px', height: '100%', cursor: 'pointer', userSelect: 'none',
        borderRight: '1px solid var(--border)', fontSize: 12, fontWeight: 600,
        color: open ? 'var(--accent-blue)' : 'var(--text-muted)',
        flexShrink: 0, position: 'relative',
      }}
      onMouseEnter={e => { if (!open) e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-hover)'; }}
      onMouseLeave={e => { if (!open) e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
    >
      Alerts
      {unread > 0 && (
        <span style={{
          minWidth: 16, height: 16, borderRadius: 8, padding: '0 4px',
          backgroundColor: 'var(--accent-red, #f85149)', color: '#fff',
          fontSize: 10, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </div>
  );

  if (!open) return btn;

  const tg = settings?.telegram || {};
  const monthOptions = buildMonthOptions(alerts);
  const filteredAlerts = monthFilter === 'all'
    ? alerts
    : alerts.filter((a) => {
      const ym = alertYearMonth(a?.created_at);
      return ym && monthKey(ym.year, ym.month) === monthFilter;
    });

  const panel = createPortal(
    <div
      ref={panelRef}
      data-cim-no-typeahead="1"
      style={{
        position: 'fixed', left: geom.left, top: geom.top, width: geom.w, height: geom.h,
        zIndex: Z_PANEL, display: 'flex', flexDirection: 'column',
        backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
        borderRadius: 6, boxShadow: '0 8px 28px rgba(0,0,0,0.5)', overflow: 'hidden',
      }}
    >
      <div
        onMouseDown={startDrag}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
          padding: '6px 10px', cursor: 'move', userSelect: 'none',
          borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)', flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>Alerts</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'nowrap', flexShrink: 0 }} onMouseDown={e => e.stopPropagation()}>
          <button
            type="button"
            onClick={markAllRead}
            style={btnSm}
          >Mark all read</button>
          <button
            type="button"
            onClick={clearAll}
            disabled={!alerts.length}
            title="Permanently delete every alert"
            style={{
              ...btnSm,
              cursor: alerts.length ? 'pointer' : 'default',
              color: alerts.length ? 'var(--accent-red, #f85149)' : 'var(--text-muted)',
              opacity: alerts.length ? 1 : 0.5,
            }}
          >Clear all</button>
          <button
            type="button"
            aria-label="Hide alerts"
            onClick={toggleOpen}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 15, lineHeight: 1, cursor: 'pointer', padding: '0 2px', flexShrink: 0 }}
          >×</button>
        </div>
      </div>

      <div style={{
        padding: '8px 10px', borderBottom: '1px solid var(--border)', flexShrink: 0,
        display: 'flex', flexDirection: 'column', gap: 8, backgroundColor: 'var(--bg-tertiary)',
      }}>
        <div style={{
          display: 'flex',
          flexWrap: 'nowrap',
          gap: 10,
          alignItems: 'center',
          justifyContent: 'flex-start',
          fontSize: 11,
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
        }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer', flexShrink: 0 }}>
            <input
              type="checkbox"
              checked={!!settings?.telegram_enabled}
              disabled={busy}
              onChange={e => patchSettings({ telegram_enabled: e.target.checked })}
            />
            Telegram
          </label>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer', flexShrink: 0 }}>
            <input
              type="checkbox"
              checked={!!settings?.browser_enabled}
              disabled={busy}
              onChange={e => patchSettings({ browser_enabled: e.target.checked })}
            />
            Browser
          </label>
          <button type="button" disabled={busy} onClick={sendTelegramTest} style={btnSm}>
            Send Telegram test
          </button>
          <button type="button" disabled={busy} onClick={enableBrowserNotifications} style={btnSm}>
            Allow browser alerts
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap',
            fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', whiteSpace: 'nowrap',
          }}>
            Your Telegram bot
            <span
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                fontSize: 10, fontWeight: 600, padding: '1px 7px', borderRadius: 999,
                flexShrink: 0,
                border: '1px solid var(--border)',
                background: (tg.connected || (tg.configured && tg.source === 'user'))
                  ? 'rgba(46, 160, 67, 0.15)'
                  : 'var(--bg-secondary)',
                color: (tg.connected || (tg.configured && tg.source === 'user'))
                  ? 'var(--accent-green, #3fb950)'
                  : 'var(--text-muted)',
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 6, height: 6, borderRadius: 3, flexShrink: 0,
                  background: (tg.connected || (tg.configured && tg.source === 'user'))
                    ? 'var(--accent-green, #3fb950)'
                    : 'var(--text-muted)',
                }}
              />
              {(tg.connected || (tg.configured && tg.source === 'user')) ? 'Connected' : 'Not connected'}
            </span>
            <button
              type="button"
              aria-label="How to get bot token and chat ID"
              title="How to set up Telegram"
              onClick={() => setTgHelpOpen(true)}
              style={{
                width: 18, height: 18, borderRadius: 9, padding: 0, flexShrink: 0,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, lineHeight: 1, cursor: 'pointer',
                border: '1px solid var(--border)',
                background: 'var(--bg-secondary)',
                color: 'var(--text-muted)',
              }}
            >?</button>
          </div>
          <div style={{
            display: 'flex',
            flexWrap: 'nowrap',
            gap: 6,
            alignItems: 'center',
            justifyContent: 'flex-start',
            whiteSpace: 'nowrap',
          }}>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              placeholder={tg.source === 'user' ? 'Replace bot token' : 'Bot token'}
              value={tgTokenDraft}
              onChange={(e) => setTgTokenDraft(e.target.value)}
              {...pctKeyProps}
              style={{ ...inputFixed, width: 200 }}
            />
            <input
              type="text"
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              placeholder={tg.source === 'user'
                ? (tg.chat_id_hint ? `Replace chat (${tg.chat_id_hint})` : 'Replace chat ID')
                : 'Chat ID'}
              value={tgChatDraft}
              onChange={(e) => setTgChatDraft(e.target.value)}
              {...pctKeyProps}
              style={{ ...inputFixed, width: 120 }}
            />
            <button type="button" disabled={busy} onClick={saveTelegramCredentials} style={btnSm}>
              Save
            </button>
            <button
              type="button"
              disabled={busy || !(tg.configured && tg.source === 'user')}
              onClick={clearTelegramCredentials}
              style={{
                ...btnSm,
                cursor: (tg.configured && tg.source === 'user') ? 'pointer' : 'default',
                color: 'var(--text-muted)',
                opacity: (tg.configured && tg.source === 'user') ? 1 : 0.5,
              }}
            >Clear</button>
          </div>
          <div style={{
            fontSize: 10,
            color: (tg.connected || (tg.configured && tg.source === 'user'))
              ? 'var(--text-secondary)'
              : 'var(--text-muted)',
            lineHeight: 1.35,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {tg.source === 'user'
              ? [
                  'Connected to this CiM account',
                  tg.bot_username || null,
                  tg.bot_name && tg.bot_name !== (tg.bot_username || '').replace(/^@/, '')
                    ? tg.bot_name
                    : null,
                  tg.chat_id_hint ? `chat ${tg.chat_id_hint}` : null,
                ].filter(Boolean).join(' · ')
              : tg.source === 'host'
                ? 'Host fallback (.env) — save your own bot above for a clear Connected status'
                : 'Not connected — tap ? for setup'}
            {statusMsg ? (
              <span style={{ color: 'var(--accent-blue)', marginLeft: 8 }}>{statusMsg}</span>
            ) : null}
          </div>
        </div>
      </div>

      <CimFormDialog
        open={tgHelpOpen}
        title="Set up your Telegram bot"
        subtitle="Each account uses its own bot. Credentials are encrypted on the server after Save."
        titleId="cim-telegram-setup-help"
        onClose={() => setTgHelpOpen(false)}
        width={CIM_DIALOG_WIDTH_WIDE}
        zIndex={Z_TG_HELP}
        footer={(
          <CimDialogButton variant="primary" onClick={() => setTgHelpOpen(false)}>
            Close
          </CimDialogButton>
        )}
      >
        <ol style={{
          margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.55,
          color: 'var(--text-primary)', display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <li>
            Open Telegram and search for <strong>@BotFather</strong>.
          </li>
          <li>
            Send <code>/newbot</code>, choose a display name and a username ending in <code>bot</code>.
          </li>
          <li>
            BotFather replies with an <strong>HTTP API token</strong> (looks like
            {' '}<code>123456:AA…</code>). Copy that into <strong>Bot token</strong> in Alerts.
          </li>
          <li>
            Open a chat with <em>your</em> new bot and send any message (e.g. <code>hi</code>)
            so Telegram creates a chat.
          </li>
          <li>
            Get your <strong>chat ID</strong>:
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              <li>
                Easiest: message <strong>@userinfobot</strong> (or similar) and copy the Id it shows, or
              </li>
              <li>
                Open
                {' '}
                <code style={{ wordBreak: 'break-all' }}>
                  https://api.telegram.org/bot&lt;YOUR_TOKEN&gt;/getUpdates
                </code>
                {' '}
                in a browser and find <code>&quot;chat&quot;:{'{'}&quot;id&quot;: …{'}'}</code>.
              </li>
            </ul>
          </li>
          <li>
            Paste the chat ID into Alerts → <strong>Save</strong> → turn <strong>Telegram</strong> on
            → <strong>Send Telegram test</strong>.
          </li>
        </ol>
        <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.45 }}>
          Never share your bot token. CiM stores it encrypted for your signed-in account only;
          it is not kept in the browser after Save.
        </p>
      </CimFormDialog>

      <div style={{
        flexShrink: 0,
        padding: '8px 10px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-tertiary)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Price targets
          <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6 }}>
            Watchlists with Notifications ON · live · Telegram
          </span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'flex-start' }}>
          <div ref={ptSymbolWrapRef} style={{ position: 'relative', flexShrink: 0 }}>
            <input
              type="text"
              placeholder="Symbol"
              disabled={busy}
              value={ptSymbol}
              onChange={(e) => {
                setPtSymbol(e.target.value.toUpperCase());
                setPtActiveIdx(-1);
              }}
              onFocus={() => {
                if (ptSuggestions.length) setPtSuggestOpen(true);
              }}
              onKeyDown={onPtSymbolKeyDown}
              autoComplete="off"
              spellCheck={false}
              {...pctKeyProps}
              style={{ ...inputFixed, width: 100, fontFamily: 'var(--font-mono)', fontWeight: 600 }}
            />
            {ptSuggestOpen && ptSuggestions.length > 0 ? (
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: '100%',
                  marginTop: 2,
                  zIndex: 20,
                  minWidth: 140,
                  maxWidth: 220,
                  maxHeight: 160,
                  overflowY: 'auto',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 5,
                  boxShadow: '0 8px 20px rgba(0,0,0,0.45)',
                }}
              >
                {ptSuggestions.map((sym, i) => {
                  const active = i === ptActiveIdx;
                  return (
                    <button
                      key={sym}
                      type="button"
                      onMouseDown={(ev) => {
                        ev.preventDefault();
                        pickPtSymbol(sym);
                      }}
                      onMouseEnter={() => setPtActiveIdx(i)}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '6px 10px',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 600,
                        background: active ? 'rgba(56,139,253,0.18)' : 'transparent',
                        color: 'var(--text-primary)',
                      }}
                    >
                      {sym}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
          <select
            disabled={busy}
            value={ptDirection}
            onChange={(e) => setPtDirection(e.target.value)}
            title={ptDirection === 'below' ? 'Below or equal (≤)' : 'Above or equal (≥)'}
            style={{
              ...inputFixed,
              width: 168,
              minWidth: 168,
              paddingRight: 22,
              cursor: 'pointer',
              marginTop: 0,
              flexShrink: 0,
            }}
          >
            <option value="above">Above or equal (≥)</option>
            <option value="below">Below or equal (≤)</option>
          </select>
          <input
            type="number"
            placeholder="₹ level"
            min={0.01}
            step={0.05}
            disabled={busy}
            value={ptLevel}
            onChange={(e) => setPtLevel(e.target.value)}
            {...pctKeyProps}
            style={{ ...inputFixed, width: 96, minWidth: 96, flexShrink: 0 }}
          />
          <button type="button" disabled={busy} onClick={addPriceTarget} style={btnSm}>
            Arm
          </button>
        </div>
        {priceTargets.length === 0 ? (
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            No price targets yet. Symbol must be on a watchlist with Notifications enabled.
          </div>
        ) : (
          <div ref={ptListWrapRef} style={{ position: 'relative', alignSelf: 'flex-start' }}>
            <button
              type="button"
              disabled={busy}
              aria-expanded={ptListOpen}
              aria-haspopup="listbox"
              onClick={() => {
                setPtListOpen((v) => !v);
                setPtSuggestOpen(false);
              }}
              style={{
                ...btnSm,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '3px 10px',
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}
            >
              <span>
                Armed alerts ({armedTargetCount})
                {priceTargets.length !== armedTargetCount
                  ? ` · ${priceTargets.length - armedTargetCount} triggered`
                  : ''}
              </span>
              <span style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1 }} aria-hidden>
                {ptListOpen ? '▲' : '▼'}
              </span>
            </button>
            {ptListOpen ? (
              <div
                role="listbox"
                style={{
                  position: 'absolute',
                  left: 0,
                  top: '100%',
                  marginTop: 4,
                  zIndex: 25,
                  width: 'min(420px, calc(100vw - 48px))',
                  minWidth: 280,
                  maxHeight: 240,
                  overflowY: 'auto',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  boxShadow: '0 10px 28px rgba(0,0,0,0.5)',
                  padding: 4,
                }}
              >
                {sortedPriceTargets.map((t) => (
                  <div
                    key={t.id}
                    role="option"
                    aria-selected={Boolean(t.armed)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      fontSize: 11,
                      color: 'var(--text-secondary)',
                      padding: '6px 8px',
                      borderRadius: 4,
                    }}
                  >
                    <button
                      type="button"
                      title={`Open chart: ${t.symbol}`}
                      onClick={() => openAlertSymbol(t.symbol)}
                      style={{
                        fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--accent-blue, #58a6ff)',
                        minWidth: 72, textAlign: 'left',
                        background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                      }}
                    >
                      {t.symbol}
                    </button>
                    <span style={{ flex: '1 1 auto', minWidth: 0 }}>
                      {t.direction === 'below' ? '≤' : '≥'} ₹{Number(t.level).toLocaleString('en-IN')}
                    </span>
                    <span style={{
                      color: t.armed ? 'var(--accent-green, #3fb950)' : 'var(--text-muted)',
                      flexShrink: 0,
                      fontSize: 10,
                      textTransform: 'uppercase',
                      letterSpacing: 0.3,
                    }}>
                      {t.armed ? 'armed' : 'triggered'}
                    </span>
                    {!t.armed ? (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => rearmPriceTarget(t.id)}
                        style={btnSm}
                      >
                        Re-arm
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => deletePriceTarget(t.id)}
                      style={btnSm}
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </div>

      <div style={{
        padding: '6px 10px', borderBottom: '1px solid var(--border)', flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text-secondary)',
      }}>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          Month
          <select
            value={monthFilter}
            onChange={(e) => setMonthFilter(e.target.value)}
            style={{
              fontSize: 11, padding: '2px 6px', borderRadius: 4,
              border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
            }}
          >
            <option value="all">All months</option>
            {monthOptions.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
        </label>
        <span style={{ color: 'var(--text-muted)' }}>
          {filteredAlerts.length} shown{monthFilter !== 'all' ? ` · ${alerts.length} total` : ''}
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {alerts.length === 0 ? (
          <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>
            No alerts yet. Enable a watchlist’s Notifications toggle or Earnings notifications.
          </div>
        ) : filteredAlerts.length === 0 ? (
          <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>
            No alerts in this month. Choose All months or another month.
          </div>
        ) : (
          filteredAlerts.map((a) => (
            <div
              key={a.id}
              onClick={() => {
                if (!a.read) markOneRead(a.id);
                if (a.symbol) openAlertSymbol(a.symbol);
              }}
              style={{
                padding: '10px 12px',
                borderBottom: '1px solid var(--border-light, var(--border))',
                cursor: a.symbol || !a.read ? 'pointer' : 'default',
                backgroundColor: a.read ? 'transparent' : 'rgba(56,139,253,0.08)',
              }}
              title={a.symbol ? `Open chart: ${String(a.symbol).toUpperCase()}` : undefined}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 2 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{a.title}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{formatWhen(a.created_at)}</span>
                  <button
                    type="button"
                    title="Delete this alert"
                    aria-label="Delete alert"
                    onClick={(e) => { e.stopPropagation(); deleteOne(a.id); }}
                    style={{
                      fontSize: 11, padding: '0 6px', lineHeight: '18px', borderRadius: 4, cursor: 'pointer',
                      border: '1px solid var(--border)', background: 'var(--bg-secondary)',
                      color: 'var(--text-muted)',
                    }}
                  >Delete</button>
                </div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.35 }}>{a.body}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                {a.source}{a.watchlist_name ? ` · ${a.watchlist_name}` : ''}
                {a.symbol ? (
                  <>
                    {' · '}
                    <button
                      type="button"
                      title={`Open chart: ${String(a.symbol).toUpperCase()}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!a.read) markOneRead(a.id);
                        openAlertSymbol(a.symbol);
                      }}
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 600,
                        color: 'var(--accent-blue, #58a6ff)',
                        background: 'none',
                        border: 'none',
                        padding: 0,
                        cursor: 'pointer',
                        fontSize: 10,
                      }}
                    >
                      {String(a.symbol).toUpperCase()}
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>

      <div
        style={{
          flexShrink: 0,
          display: 'flex',
          flexWrap: 'nowrap',
          alignItems: 'center',
          justifyContent: 'flex-start',
          gap: 16,
          padding: '8px 10px',
          paddingRight: 18,
          borderTop: '1px solid var(--border)',
          backgroundColor: 'var(--bg-tertiary)',
          fontSize: 11,
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
        }}
      >
        <label
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0 }}
          title="Watchlist: alert when 1D % is at least this (up moves only)"
        >
          Watchlist +1D ≥
          <input
            type="number"
            min={0.5}
            max={50}
            step={0.5}
            autoComplete="off"
            disabled={busy}
            value={dayMoveDraft}
            onChange={(e) => setDayMoveDraft(e.target.value)}
            onBlur={() => commitPctDraft('watchlist')}
            {...pctKeyProps}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                e.currentTarget.blur();
              }
            }}
            style={pctInputStyle}
          />
          %
        </label>
        <label
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0,
            opacity: settings?.portfolio_notifications_enabled ? 1 : 0.85,
          }}
          title={settings?.portfolio_notifications_enabled
            ? 'Portfolio: alert when 1D % is at least this (up moves only)'
            : 'Set threshold now — turn on Portfolio notifications on the Portfolio page to arm alerts'}
        >
          Portfolio +1D ≥
          <input
            type="number"
            min={0.5}
            max={50}
            step={0.5}
            autoComplete="off"
            disabled={busy}
            value={portfolioMoveDraft}
            onChange={(e) => setPortfolioMoveDraft(e.target.value)}
            onBlur={() => commitPctDraft('portfolio')}
            {...pctKeyProps}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                e.currentTarget.blur();
              }
            }}
            style={pctInputStyle}
          />
          %
        </label>
      </div>

      <div
        onMouseDown={startResize}
        style={{
          position: 'absolute', right: 0, bottom: 0, width: 14, height: 14, cursor: 'nwse-resize',
        }}
        title="Resize"
      />
    </div>,
    document.body,
  );

  return (
    <>
      {btn}
      {panel}
    </>
  );
}
