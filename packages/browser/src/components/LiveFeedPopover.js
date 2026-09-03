import React, { useCallback, useEffect, useRef, useState } from 'react';

const EMPTY = {
  enabled: false,
  busy: false,
  context: 'focus',
  contextLabel: 'this page',
  pageId: '',
  symbol: '',
  detail: 'Live feed off — open a page, then flip the switch',
  tone: 'idle',
  source: { label: 'Upstox', detail: '' },
  earningsToday: false,
};

function getControl() {
  if (typeof window === 'undefined') return null;
  return window.CiMLiveFeedControl || null;
}

function FeedSwitch({ checked, disabled, onClick, ariaLabel, title }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      title={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        position: 'relative',
        width: 44,
        height: 24,
        flexShrink: 0,
        borderRadius: 12,
        border: '1px solid var(--border)',
        backgroundColor: checked ? 'var(--accent-green, #238636)' : 'var(--bg-primary)',
        cursor: disabled ? 'wait' : 'pointer',
        padding: 0,
        opacity: disabled ? 0.65 : 1,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: 2,
          width: 18,
          height: 18,
          borderRadius: '50%',
          backgroundColor: '#fff',
          boxShadow: '0 1px 2px rgba(0,0,0,0.35)',
          transform: checked ? 'translateX(20px)' : 'translateX(0)',
          transition: 'transform 0.15s ease',
        }}
      />
    </button>
  );
}

/**
 * Top-bar Live Feed chip + popover.
 * Scope follows the active page — no Mode dropdown.
 */
export default function LiveFeedPopover({
  knowledgeBaseOpen = false,
  settingsOpen = false,
  onOpenChange,
}) {
  const wrapRef = useRef(null);
  const btnRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [menuRect, setMenuRect] = useState(null);
  const [feed, setFeed] = useState(() => getControl()?.getSnapshot?.() || EMPTY);

  useEffect(() => {
    let unsub = null;
    let intervalId = null;

    function attach(ctrl) {
      if (!ctrl?.subscribe) return false;
      unsub = ctrl.subscribe((snap) => setFeed(snap || EMPTY));
      return true;
    }

    if (!attach(getControl())) {
      let tries = 0;
      intervalId = window.setInterval(() => {
        tries += 1;
        if (attach(getControl()) || tries > 40) {
          window.clearInterval(intervalId);
          intervalId = null;
        }
      }, 100);
    }

    return () => {
      if (intervalId) window.clearInterval(intervalId);
      try { unsub?.(); } catch { /* ignore */ }
    };
  }, []);

  const closeMenu = useCallback(() => {
    setOpen(false);
    setMenuRect(null);
    try { onOpenChange?.(false); } catch { /* ignore */ }
  }, [onOpenChange]);

  const toggleMenu = useCallback(() => {
    setOpen((prev) => {
      if (prev) {
        setMenuRect(null);
        try { onOpenChange?.(false); } catch { /* ignore */ }
        return false;
      }
      const btn = btnRef.current;
      if (!btn) {
        try { onOpenChange?.(true); } catch { /* ignore */ }
        return true;
      }
      const r = btn.getBoundingClientRect();
      setMenuRect({
        top: r.bottom + 4,
        left: Math.max(8, r.right - 300),
        width: 300,
      });
      try { onOpenChange?.(true); } catch { /* ignore */ }
      return true;
    });
  }, [onOpenChange]);

  useEffect(() => {
    if (!open) return undefined;
    function onForceClose() { closeMenu(); }
    window.addEventListener('cim:live-feed-popover-close', onForceClose);
    return () => window.removeEventListener('cim:live-feed-popover-close', onForceClose);
  }, [open, closeMenu]);

  useEffect(() => {
    if (knowledgeBaseOpen || settingsOpen) closeMenu();
  }, [knowledgeBaseOpen, settingsOpen, closeMenu]);

  useEffect(() => {
    if (!open) return undefined;
    function onDocMouseDown(e) {
      const wrap = wrapRef.current;
      if (wrap && wrap.contains(e.target)) return;
      closeMenu();
    }
    function onEsc(e) {
      if (e.key === 'Escape') closeMenu();
    }
    document.addEventListener('mousedown', onDocMouseDown);
    window.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      window.removeEventListener('keydown', onEsc);
    };
  }, [open, closeMenu]);

  const ctrl = getControl();
  const isOn = !!feed.enabled;
  const isErr = feed.tone === 'err' || feed.tone === 'error';
  const chipLabel = isOn
    ? (feed.contextLabel || 'Live')
    : 'Live';
  const chipSub = isOn ? 'ON' : 'Off';

  return (
    <div ref={wrapRef} style={{ position: 'relative', flexShrink: 0, display: 'flex', alignItems: 'stretch' }}>
      <button
        ref={btnRef}
        type="button"
        onClick={toggleMenu}
        title={feed.detail || 'Live Feed'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          padding: '0 12px',
          borderRight: '1px solid var(--border)',
          background: open ? 'var(--bg-hover)' : 'transparent',
          color: isErr ? 'var(--accent-red)' : (isOn ? 'var(--text-primary)' : 'var(--text-muted)'),
          fontSize: 12,
          fontWeight: 600,
          cursor: 'pointer',
          flexShrink: 0,
          whiteSpace: 'nowrap',
        }}
        onMouseEnter={(e) => {
          if (!open) e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
        }}
        onMouseLeave={(e) => {
          if (!open) e.currentTarget.style.backgroundColor = 'transparent';
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 99,
            background: isErr
              ? 'var(--accent-red, #f85149)'
              : (isOn ? 'var(--accent-green, #2ea043)' : 'var(--text-muted)'),
            boxShadow: isOn && !isErr ? '0 0 0 2px rgba(46,160,67,0.2)' : 'none',
            flexShrink: 0,
          }}
        />
        <span>{chipLabel}</span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.04em',
            color: isOn && !isErr ? 'var(--accent-green, #3fb950)' : 'var(--text-muted)',
          }}
        >
          {chipSub}
        </span>
      </button>

      {open && menuRect && (
        <div
          style={{
            position: 'fixed',
            top: menuRect.top,
            left: menuRect.left,
            width: menuRect.width,
            zIndex: 200000,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.55)',
            overflow: 'visible',
            padding: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 99,
                  background: isErr
                    ? 'var(--accent-red)'
                    : (isOn ? 'var(--accent-green)' : 'var(--text-muted)'),
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>Live Feed</span>
            </div>
            <FeedSwitch
              checked={isOn}
              disabled={!!feed.busy && !isOn}
              onClick={() => ctrl?.toggle?.()}
              ariaLabel="Toggle live feed"
              title={isOn ? 'Turn live off' : 'Turn live on for this page'}
            />
          </div>

          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              fontSize: 10,
              fontWeight: 700,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            Scope
            <div
              style={{
                minHeight: 30,
                display: 'flex',
                alignItems: 'center',
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                padding: '0 10px',
                fontSize: 12,
                fontWeight: 600,
                textTransform: 'none',
                letterSpacing: 0,
              }}
            >
              {feed.contextLabel || 'this page'}
            </div>
          </div>

          <div
            style={{
              minHeight: 32,
              padding: '7px 8px',
              borderRadius: 6,
              background: 'var(--bg-tertiary)',
              color: isErr ? 'var(--accent-red)' : 'var(--text-secondary)',
              fontSize: 11,
              wordBreak: 'break-word',
            }}
          >
            {feed.detail}
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 10 }}>
            Source: {feed.source?.label || 'Upstox'}
            {feed.source?.detail ? ` — ${feed.source.detail}` : ''}
          </div>
        </div>
      )}
    </div>
  );
}
