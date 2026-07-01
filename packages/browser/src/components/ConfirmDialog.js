import React from 'react';
import { CimDialogButton, CimFormDialog } from './cimDialogChrome';

/**
 * In-app confirmation dialog (replaces window.confirm for admin actions).
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) {
  return (
    <CimFormDialog
      open={open}
      title={title}
      titleId="cim-confirm-title"
      onClose={onCancel}
      footer={(
        <>
          <CimDialogButton onClick={onCancel}>{cancelLabel}</CimDialogButton>
          <CimDialogButton variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>
            {confirmLabel}
          </CimDialogButton>
        </>
      )}
    >
      <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
        {message}
      </p>
    </CimFormDialog>
  );
}

/**
 * Promise-based helper for confirm flows.
 */
export function askConfirm(setConfirmState, { title, message, confirmLabel, danger = false }) {
  return new Promise(resolve => {
    setConfirmState({
      title,
      message,
      confirmLabel,
      danger,
      onConfirm: () => {
        setConfirmState(null);
        resolve(true);
      },
      onCancel: () => {
        setConfirmState(null);
        resolve(false);
      },
    });
  });
}
