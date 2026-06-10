import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchKnowledgeBasePage } from '../api/knowledgeBase';
import { resolveKnowledgeBaseGuideId } from '../content/knowledgeBasePages';
import {
  KB_SIDEBAR_CHROME_PX,
  clampKnowledgeBaseWidthPx,
  loadKnowledgeBaseWidthRatio,
  saveKnowledgeBaseWidthRatio,
  widthPxFromRatio,
} from '../utils/knowledgeBasePanelPrefs';
import { CIM_CHROME_INTRO_READY_EVENT } from '../chartEvents';

const PANEL_SLIDE_MS = 520;
const CHROME_INTRO_SESSION_KEY = 'cim-kb-chrome-intro-seen';
const CHROME_INTRO_DURATION_MS = 10500;
const CHROME_INTRO_FALLBACK_MS = 3000;

function KnowledgeBaseRailArrow({ open }) {
  return (
    <span className="cim-kb-sidebar-arrow" aria-hidden="true">
      <svg width="7" height="10" viewBox="0 0 10 14" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        {open ? (
          <path d="M2 1 L9 7 L2 13 Z" />
        ) : (
          <path d="M8 1 L1 7 L8 13 Z" />
        )}
      </svg>
    </span>
  );
}

export default function CiMKnowledgeBase({
  mainColumnRef,
  open,
  onOpenChange,
  view,
  contentRevision = 0,
  previewContent = null,
}) {
  const resizeRef = useRef({ active: false, startX: 0, startWidth: 0 });
  const panelWidthRef = useRef(0);
  const panelRef = useRef(null);
  const unmountTimerRef = useRef(null);

  const [panelWidthPx, setPanelWidthPx] = useState(() => {
    if (typeof window === 'undefined') return 360;
    return widthPxFromRatio(window.innerWidth - KB_SIDEBAR_CHROME_PX, loadKnowledgeBaseWidthRatio());
  });
  const [isResizing, setIsResizing] = useState(false);
  const [panelMounted, setPanelMounted] = useState(false);
  const [pageContent, setPageContent] = useState(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState('');
  const [chromeIntroActive, setChromeIntroActive] = useState(false);

  const guideId = resolveKnowledgeBaseGuideId(view);

  panelWidthRef.current = panelWidthPx;

  const unmountPanel = useCallback(() => {
    if (unmountTimerRef.current) {
      clearTimeout(unmountTimerRef.current);
      unmountTimerRef.current = null;
    }
    setPanelMounted(false);
  }, []);

  const getMainColumnWidth = useCallback(() => {
    const el = mainColumnRef?.current;
    if (el && el.clientWidth > 0) return el.clientWidth;
    return Math.max(1, (typeof window !== 'undefined' ? window.innerWidth : 1200) - KB_SIDEBAR_CHROME_PX);
  }, [mainColumnRef]);

  const syncWidthFromStorage = useCallback(() => {
    const col = getMainColumnWidth();
    const ratio = loadKnowledgeBaseWidthRatio();
    setPanelWidthPx(widthPxFromRatio(col, ratio));
  }, [getMainColumnWidth]);

  useEffect(() => {
    syncWidthFromStorage();
  }, [syncWidthFromStorage]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    if (sessionStorage.getItem(CHROME_INTRO_SESSION_KEY)) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      sessionStorage.setItem(CHROME_INTRO_SESSION_KEY, '1');
      return undefined;
    }

    let started = false;
    let stopTimer = null;

    const beginIntro = () => {
      if (started) return;
      started = true;
      sessionStorage.setItem(CHROME_INTRO_SESSION_KEY, '1');
      setChromeIntroActive(true);
      stopTimer = window.setTimeout(() => setChromeIntroActive(false), CHROME_INTRO_DURATION_MS);
    };

    const onReady = () => beginIntro();
    window.addEventListener(CIM_CHROME_INTRO_READY_EVENT, onReady);
    const fallbackTimer = window.setTimeout(beginIntro, CHROME_INTRO_FALLBACK_MS);

    return () => {
      window.removeEventListener(CIM_CHROME_INTRO_READY_EVENT, onReady);
      window.clearTimeout(fallbackTimer);
      if (stopTimer) window.clearTimeout(stopTimer);
    };
  }, []);

  useEffect(() => {
    if (open) {
      if (unmountTimerRef.current) {
        clearTimeout(unmountTimerRef.current);
        unmountTimerRef.current = null;
      }
      setPanelMounted(true);
      return undefined;
    }

    if (!panelMounted) return undefined;

    unmountTimerRef.current = window.setTimeout(() => {
      unmountTimerRef.current = null;
      setPanelMounted(false);
    }, PANEL_SLIDE_MS + 50);

    return () => {
      if (unmountTimerRef.current) {
        clearTimeout(unmountTimerRef.current);
        unmountTimerRef.current = null;
      }
    };
  }, [open, panelMounted]);

  useEffect(() => () => {
    if (unmountTimerRef.current) {
      clearTimeout(unmountTimerRef.current);
    }
  }, []);

  useEffect(() => {
    const onResize = () => {
      if (resizeRef.current.active) return;
      const col = getMainColumnWidth();
      const ratio = loadKnowledgeBaseWidthRatio();
      setPanelWidthPx(widthPxFromRatio(col, ratio));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [getMainColumnWidth]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') onOpenChange(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!isResizing) return;
    const onMove = (e) => {
      if (!resizeRef.current.active) return;
      const col = getMainColumnWidth();
      const delta = resizeRef.current.startX - e.clientX;
      const next = clampKnowledgeBaseWidthPx(resizeRef.current.startWidth + delta, col);
      setPanelWidthPx(next);
    };
    const onUp = () => {
      if (!resizeRef.current.active) return;
      resizeRef.current.active = false;
      setIsResizing(false);
      saveKnowledgeBaseWidthRatio(panelWidthRef.current, getMainColumnWidth());
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
  }, [isResizing, getMainColumnWidth]);

  const toggle = useCallback(() => {
    onOpenChange(!open);
  }, [open, onOpenChange]);

  const close = useCallback(() => {
    onOpenChange(false);
  }, [onOpenChange]);

  const onResizeMouseDown = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    resizeRef.current = {
      active: true,
      startX: e.clientX,
      startWidth: panelWidthRef.current,
    };
    setIsResizing(true);
  }, []);

  const onPanelClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  const onPanelAnimationEnd = useCallback((e) => {
    if (e.target !== panelRef.current) return;
    if (!open) unmountPanel();
  }, [open, unmountPanel]);

  useEffect(() => {
    if (previewContent) {
      setPageContent(previewContent);
      setContentLoading(false);
      setContentError('');
      return undefined;
    }

    let cancelled = false;
    setContentLoading(true);
    setContentError('');
    fetchKnowledgeBasePage(guideId)
      .then((page) => {
        if (cancelled) return;
        setPageContent(page);
      })
      .catch((err) => {
        if (cancelled) return;
        setPageContent(null);
        setContentError(err?.response?.data?.detail || err?.message || 'Failed to load Knowledge Base.');
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false);
      });

    return () => { cancelled = true; };
  }, [guideId, contentRevision, previewContent]);

  const content = previewContent || pageContent;

  const overlay = panelMounted ? createPortal(
    <>
      {open && (
        <div
          className="cim-kb-scrim"
          role="presentation"
          aria-hidden="true"
          onClick={close}
        />
      )}
      <div
        ref={panelRef}
        className={[
          'cim-kb-panel',
          'cim-kb-panel--slide',
          open ? 'cim-kb-panel--open' : 'cim-kb-panel--closed',
          !isResizing ? 'cim-kb-panel--width-animate' : '',
        ].filter(Boolean).join(' ')}
        style={{ width: panelWidthPx }}
        role="dialog"
        aria-modal={open ? 'true' : 'false'}
        aria-hidden={open ? 'false' : 'true'}
        aria-labelledby={open ? 'cim-kb-header-title' : undefined}
        onClick={onPanelClick}
        onAnimationEnd={onPanelAnimationEnd}
      >
        {open && (
          <>
            <div
              className={[
                'cim-kb-resize-handle',
                isResizing ? 'cim-kb-resize-handle--active' : '',
              ].filter(Boolean).join(' ')}
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize knowledge base panel"
              onMouseDown={onResizeMouseDown}
            />
            <div className="cim-kb-header">
              <div id="cim-kb-header-title" className="cim-kb-header-title">
                {contentLoading && !content ? 'Loading…' : (content?.title || 'Charts In Motion Knowledge Base')}
              </div>
              <button
                type="button"
                className="cim-kb-close-btn"
                aria-label="Close Charts In Motion Knowledge Base"
                onClick={close}
              >
                ×
              </button>
            </div>
            <div className="cim-kb-body">
              {contentLoading && !content && (
                <p className="cim-kb-section-paragraph">Loading guide…</p>
              )}
              {contentError && !previewContent && (
                <p className="cim-kb-section-paragraph" style={{ color: '#f85149' }}>
                  {contentError}
                </p>
              )}
              {content?.sections?.map((section, sectionIdx) => (
                <section key={`${section.heading}-${sectionIdx}`} className="cim-kb-section">
                  <h2 className="cim-kb-section-heading">{section.heading}</h2>
                  {section.paragraphs.map((paragraph, idx) => (
                    <p key={idx} className="cim-kb-section-paragraph">
                      {paragraph}
                    </p>
                  ))}
                </section>
              ))}
            </div>
          </>
        )}
      </div>
    </>,
    document.body,
  ) : null;

  return (
    <>
      <button
        type="button"
        className={[
          'cim-kb-sidebar-chrome',
          open ? 'cim-kb-sidebar-chrome--open' : '',
          chromeIntroActive ? 'cim-kb-sidebar-chrome--intro' : '',
        ].filter(Boolean).join(' ')}
        aria-label={open ? 'Close Charts In Motion Knowledge Base' : 'Open Charts In Motion Knowledge Base'}
        aria-expanded={open}
        aria-controls="cim-kb-header-title"
        onClick={toggle}
      >
        {chromeIntroActive ? (
          <>
            <span className="cim-kb-chrome-glow cim-kb-chrome-glow--up" aria-hidden="true" />
            <span className="cim-kb-chrome-glow cim-kb-chrome-glow--down" aria-hidden="true" />
          </>
        ) : null}
        <KnowledgeBaseRailArrow open={open} />
      </button>
      {overlay}
    </>
  );
}
