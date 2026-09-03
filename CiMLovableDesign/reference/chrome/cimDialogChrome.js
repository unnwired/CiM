import React, { useEffect } from 'react';

/** General admin / confirm dialog chrome — see docs/standards/CIM_UI_STANDARD.md */
export const CIM_BTN_HEIGHT = 28;
export const CIM_FORM_GAP = 8;
export const CIM_FORM_INNER_GAP = 4;
export const CIM_DIALOG_WIDTH = 420;
export const CIM_DIALOG_WIDTH_WIDE = 520;

export const cimDialogOverlayStyle = {
  position: 'fixed',
  inset: 0,
  zIndex: 10000,
  background: 'rgba(0,0,0,0.55)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

export const cimDialogShellStyle = {
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '16px 20px 18px',
  width: CIM_DIALOG_WIDTH,
  maxWidth: '92vw',
  maxHeight: '85vh',
  overflow: 'auto',
  boxSizing: 'border-box',
  boxShadow: '0 12px 40px rgba(0,0,0,0.45)',
};

export const cimDialogTitleStyle = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
  margin: 0,
  lineHeight: 1.3,
};

export const cimDialogSubtitleStyle = {
  fontSize: 11,
  color: 'var(--text-muted)',
  margin: `${CIM_FORM_INNER_GAP}px 0 ${CIM_FORM_GAP}px`,
  lineHeight: 1.45,
};

export const cimDialogBodyStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: CIM_FORM_GAP,
};

export const cimDialogFooterStyle = {
  display: 'flex',
  justifyContent: 'flex-end',
  alignItems: 'center',
  flexWrap: 'nowrap',
  gap: CIM_FORM_GAP,
  marginTop: CIM_FORM_GAP + 4,
  paddingTop: CIM_FORM_GAP + 4,
  borderTop: '1px solid var(--border-light)',
};

export const cimSectionLabelStyle = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: CIM_FORM_INNER_GAP,
};

export const cimDialogErrorStyle = {
  marginTop: CIM_FORM_INNER_GAP,
  fontSize: 11,
  color: 'var(--accent-red)',
  lineHeight: 1.35,
  whiteSpace: 'pre-wrap',
};

const cimBtnBase = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: CIM_BTN_HEIGHT,
  minHeight: CIM_BTN_HEIGHT,
  minWidth: 72,
  padding: '0 14px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  whiteSpace: 'nowrap',
  boxSizing: 'border-box',
  borderRadius: 4,
  lineHeight: 1,
};

export function cimDialogSecondaryBtn(disabled) {
  return {
    ...cimBtnBase,
    background: 'var(--bg-tertiary)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.55 : 1,
  };
}

export function cimDialogPrimaryBtn(disabled) {
  return {
    ...cimBtnBase,
    fontWeight: 600,
    background: 'var(--accent-blue)',
    border: '1px solid transparent',
    color: '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };
}

export function cimDialogDangerBtn(disabled) {
  return {
    ...cimBtnBase,
    fontWeight: 600,
    background: 'var(--accent-red)',
    border: '1px solid transparent',
    color: '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };
}

export function cimChipButtonStyle(active, disabled = false) {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 24,
    minHeight: 24,
    padding: '0 8px',
    fontSize: 10,
    fontWeight: active ? 600 : 400,
    fontFamily: 'var(--font-sans)',
    borderRadius: 4,
    border: `1px solid ${active ? 'var(--accent-blue)' : 'var(--border-light)'}`,
    background: active ? 'rgba(56, 139, 253, 0.12)' : 'var(--bg-tertiary)',
    color: active ? 'var(--accent-blue)' : 'var(--text-muted)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.55 : 1,
  };
}

export function CimDialogButton({
  variant = 'secondary',
  disabled = false,
  onClick,
  type = 'button',
  title,
  children,
}) {
  const style = variant === 'primary'
    ? cimDialogPrimaryBtn(disabled)
    : variant === 'danger'
      ? cimDialogDangerBtn(disabled)
      : cimDialogSecondaryBtn(disabled);
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={style} title={title}>
      {children}
    </button>
  );
}

export function CimFormDialog({
  open,
  title,
  subtitle,
  titleId,
  onClose,
  children,
  error,
  footer,
  width = CIM_DIALOG_WIDTH,
  closeOnOverlay = true,
  closeOnEscape = true,
  zIndex,
}) {
  useEffect(() => {
    if (!open || !closeOnEscape || !onClose) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, closeOnEscape, onClose]);

  if (!open) return null;

  const overlayStyle = zIndex != null ? { ...cimDialogOverlayStyle, zIndex } : cimDialogOverlayStyle;

  return (
    <div
      className="cim-dialog-backdrop"
      role="presentation"
      onClick={closeOnOverlay ? onClose : undefined}
      style={overlayStyle}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        style={{ ...cimDialogShellStyle, width }}
      >
        <h2 id={titleId} style={cimDialogTitleStyle}>{title}</h2>
        {subtitle ? <p style={cimDialogSubtitleStyle}>{subtitle}</p> : null}
        <div style={cimDialogBodyStyle}>{children}</div>
        {error ? (
          <div role="alert" aria-live="assertive" style={cimDialogErrorStyle}>
            {error}
          </div>
        ) : null}
        {footer ? <div style={cimDialogFooterStyle}>{footer}</div> : null}
      </div>
    </div>
  );
}
