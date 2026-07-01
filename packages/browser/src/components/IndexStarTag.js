import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  STAR_PRIORITY_ORDER,
  STAR_COLOR_CSS,
  cycleStarTag,
} from '../utils/indexStarTags';

const STAR_SIZE = 14;
const HOVER_DELAY_MS = 120;
const HOVER_CLOSE_MS = 180;

function StarSvg({ tag, size = STAR_SIZE }) {
  const fill = tag ? STAR_COLOR_CSS[tag] : 'none';
  const stroke = tag ? STAR_COLOR_CSS[tag] : 'var(--text-muted)';
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <path
        d="M12 2l2.9 6.9 7.4.6-5.6 4.8 1.7 7.2L12 18.8 5.6 21.4l1.7-7.2L1.7 9.5l7.4-.6L12 2z"
        fill={fill}
        stroke={stroke}
        strokeWidth={1.4}
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PickerOption({ tag, label, selected, onPick }) {
  const isClear = tag == null;
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={selected}
      onClick={(e) => {
        e.stopPropagation();
        onPick(tag);
      }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 22,
        height: 22,
        padding: 0,
        border: selected ? '1px solid var(--accent-blue)' : '1px solid var(--border)',
        borderRadius: 4,
        background: 'var(--bg-secondary)',
        cursor: 'pointer',
      }}
    >
      {isClear ? (
        <StarSvg tag={null} size={12} />
      ) : (
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: 2,
            background: STAR_COLOR_CSS[tag],
          }}
        />
      )}
    </button>
  );
}

/**
 * Cycle-click star tag + hover color picker for Indices equity rows.
 */
export default function IndexStarTag({ symbol, tag, onChange }) {
  const anchorRef = useRef(null);
  const closeTimerRef = useRef(null);
  const openTimerRef = useRef(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerRect, setPickerRect] = useState(null);

  const clearTimers = useCallback(() => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const updatePickerRect = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPickerRect({
      top: r.bottom + 4,
      left: Math.max(8, r.left - 40),
    });
  }, []);

  const openPicker = useCallback(() => {
    clearTimers();
    updatePickerRect();
    setPickerOpen(true);
  }, [clearTimers, updatePickerRect]);

  const scheduleClose = useCallback(() => {
    clearTimers();
    closeTimerRef.current = setTimeout(() => setPickerOpen(false), HOVER_CLOSE_MS);
  }, [clearTimers]);

  const scheduleOpen = useCallback(() => {
    clearTimers();
    openTimerRef.current = setTimeout(openPicker, HOVER_DELAY_MS);
  }, [clearTimers, openPicker]);

  useEffect(() => () => clearTimers(), [clearTimers]);

  useEffect(() => {
    if (!pickerOpen) return undefined;
    const onScroll = () => updatePickerRect();
    window.addEventListener('resize', onScroll);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      window.removeEventListener('resize', onScroll);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [pickerOpen, updatePickerRect]);

  function handleClick(e) {
    e.stopPropagation();
    if (!symbol || !onChange) return;
    onChange(symbol, cycleStarTag(tag));
  }

  function handlePick(nextTag) {
    if (!symbol || !onChange) return;
    onChange(symbol, nextTag);
    setPickerOpen(false);
  }

  const ariaLabel = tag ? `Index tag: ${tag}` : 'Index tag: none';

  const picker = pickerOpen && pickerRect && typeof document !== 'undefined'
    ? createPortal(
      <div
        role="listbox"
        aria-label="Index tag color"
        onMouseEnter={() => {
          if (closeTimerRef.current) {
            clearTimeout(closeTimerRef.current);
            closeTimerRef.current = null;
          }
        }}
        onMouseLeave={scheduleClose}
        style={{
          position: 'fixed',
          top: pickerRect.top,
          left: pickerRect.left,
          zIndex: 300001,
          display: 'flex',
          gap: 4,
          padding: '4px 6px',
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          boxShadow: '0 4px 12px rgba(0,0,0,0.35)',
        }}
      >
        <PickerOption tag={null} label="Clear tag" selected={!tag} onPick={handlePick} />
        {STAR_PRIORITY_ORDER.map((c) => (
          <PickerOption
            key={c}
            tag={c}
            label={`${c.charAt(0).toUpperCase()}${c.slice(1)} tag`}
            selected={tag === c}
            onPick={handlePick}
          />
        ))}
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        aria-label={ariaLabel}
        onClick={handleClick}
        onMouseEnter={scheduleOpen}
        onMouseLeave={scheduleClose}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 18,
          height: 18,
          padding: 0,
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        <StarSvg tag={tag} />
      </button>
      {picker}
    </>
  );
}
