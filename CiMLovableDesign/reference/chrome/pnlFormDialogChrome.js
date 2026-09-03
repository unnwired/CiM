import React from 'react';

export const PNL_FORM_DIALOG_WIDTH = 252;
export const PNL_FORM_DIALOG_WIDTH_WIDE = 400;

export const PNL_BTN_HEIGHT = 28;

/** Single vertical rhythm for P&L form dialogs — children rely on column gap, not extra margins. */
export const PNL_FORM_GAP = 8;

/** Tight inset: field label → control, paired inputs in a row, lines inside inset boxes. */
export const PNL_FORM_INNER_GAP = 4;

export const pnlFormOverlayStyle = {
  position: 'fixed',
  inset: 0,
  zIndex: 300000,
  background: 'rgba(0,0,0,0.55)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

export const pnlFormShellStyle = {
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '14px 16px 16px',
  width: PNL_FORM_DIALOG_WIDTH,
  maxWidth: '92vw',
  boxSizing: 'border-box',
  boxShadow: '0 12px 40px rgba(0,0,0,0.45)',
};

export const pnlFormTitleStyle = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: PNL_FORM_INNER_GAP,
  lineHeight: 1.3,
};

export const pnlFormSubtitleStyle = {
  fontSize: 10,
  color: 'var(--text-muted)',
  marginBottom: PNL_FORM_GAP,
  lineHeight: 1.35,
};

export const pnlFormFieldsColStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: PNL_FORM_GAP,
};

export const pnlFormFieldLabelStyle = {
  fontSize: 10,
  color: 'var(--text-muted)',
  marginBottom: PNL_FORM_INNER_GAP,
};

export const pnlFormFieldRowStyle = {
  display: 'grid',
  gridTemplateColumns: '1fr 72px',
  gap: PNL_FORM_INNER_GAP,
};

export const pnlFormInsetBoxStyle = {
  padding: `${PNL_FORM_GAP}px 10px`,
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border-light)',
  borderRadius: 4,
  display: 'flex',
  flexDirection: 'column',
  gap: PNL_FORM_INNER_GAP,
};

export const pnlFormFieldStyle = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '6px 8px',
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontSize: 12,
};

export const pnlFormMonoFieldStyle = {
  ...pnlFormFieldStyle,
  fontFamily: 'var(--font-mono)',
};

export const pnlFormFooterStyle = {
  display: 'flex',
  justifyContent: 'flex-end',
  alignItems: 'center',
  flexWrap: 'nowrap',
  gap: PNL_FORM_GAP,
  marginTop: PNL_FORM_GAP,
  paddingTop: PNL_FORM_GAP,
  borderTop: '1px solid var(--border-light)',
};

export const pnlFormFooterSplitStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  flexWrap: 'nowrap',
  gap: PNL_FORM_GAP,
  marginTop: PNL_FORM_GAP,
  paddingTop: PNL_FORM_GAP,
  borderTop: '1px solid var(--border-light)',
};

const pnlBtnBase = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: PNL_BTN_HEIGHT,
  minHeight: PNL_BTN_HEIGHT,
  padding: '0 12px',
  fontSize: 11,
  fontFamily: 'var(--font-sans)',
  whiteSpace: 'nowrap',
  boxSizing: 'border-box',
  borderRadius: 4,
  lineHeight: 1,
};

export function pnlFormCancelBtn(disabled) {
  return {
    ...pnlBtnBase,
    background: 'var(--bg-tertiary)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  };
}

export function pnlFormPrimaryBtn(disabled) {
  return {
    ...pnlBtnBase,
    fontWeight: 600,
    background: 'var(--accent-blue)',
    border: 'none',
    color: '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };
}

export function PnlDialogButton({
  variant = 'secondary',
  disabled = false,
  onClick,
  type = 'button',
  title,
  children,
}) {
  const style = variant === 'primary' ? pnlFormPrimaryBtn(disabled) : pnlFormCancelBtn(disabled);
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={style} title={title}>
      {children}
    </button>
  );
}

/** Panel / page toolbar — same chrome as dialog buttons (28px, 11px). */
export const PnlToolbarButton = PnlDialogButton;

const pnlCompactBtnBase = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: 22,
  minHeight: 22,
  padding: '0 8px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'var(--font-sans)',
  whiteSpace: 'nowrap',
  boxSizing: 'border-box',
  borderRadius: 4,
  lineHeight: 1,
};

export function pnlGridActionBtn(disabled) {
  return {
    ...pnlCompactBtnBase,
    background: 'var(--bg-tertiary)',
    border: '1px solid var(--border)',
    color: disabled ? 'var(--text-muted)' : 'var(--accent-blue)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  };
}

export function PnlGridActionButton({ disabled = false, onClick, children, title }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={pnlGridActionBtn(disabled)} title={title}>
      {children}
    </button>
  );
}

export const pnlFormErrorStyle = {
  marginTop: PNL_FORM_GAP,
  fontSize: 11,
  color: 'var(--accent-red)',
  lineHeight: 1.35,
};

export const pnlFormPickListStyle = {
  maxHeight: 108,
  overflow: 'auto',
  border: '1px solid var(--border)',
  borderRadius: 4,
};

export function PnlFormDialog({
  title,
  subtitle,
  titleId,
  onClose,
  children,
  error,
  footer,
  footerStyle = pnlFormFooterStyle,
  width = PNL_FORM_DIALOG_WIDTH,
}) {
  return (
    <div role="presentation" onClick={onClose} style={pnlFormOverlayStyle}>
      <div
        role="dialog"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        style={{ ...pnlFormShellStyle, width }}
      >
        <div
          id={titleId}
          style={{ ...pnlFormTitleStyle, marginBottom: subtitle ? PNL_FORM_INNER_GAP : PNL_FORM_GAP }}
        >
          {title}
        </div>
        {subtitle ? <div style={pnlFormSubtitleStyle}>{subtitle}</div> : null}
        <div style={pnlFormFieldsColStyle}>{children}</div>
        {error ? <div style={pnlFormErrorStyle}>{error}</div> : null}
        {footer ? <div style={footerStyle}>{footer}</div> : null}
      </div>
    </div>
  );
}
