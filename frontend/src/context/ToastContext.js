import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = useCallback((message, ms = 3500) => {
    setToastMessage(message);
    if (ms > 0) {
      window.setTimeout(() => setToastMessage(null), ms);
    }
  }, []);

  const value = useMemo(
    () => ({ toastMessage, setToastMessage, showToast }),
    [toastMessage, showToast],
  );

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return ctx;
}
