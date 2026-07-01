import supportUpiQr from '../assets/support-upi-qr.jpg';

export const SUPPORT_QR_DEV_URL = supportUpiQr;

let prefetchPromise = null;

/** Warm the browser image cache for the dev/showcase QR asset. */
export function prefetchDevSupportQr() {
  if (prefetchPromise) return prefetchPromise;
  prefetchPromise = new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => resolve(SUPPORT_QR_DEV_URL);
    img.onerror = () => {
      prefetchPromise = null;
      reject(new Error('Support QR failed to load'));
    };
    img.src = SUPPORT_QR_DEV_URL;
  });
  return prefetchPromise;
}

export function isDevSupportQrPrefetched() {
  return prefetchPromise != null;
}
