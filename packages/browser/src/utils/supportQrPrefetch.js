/* eslint-disable global-require */

/**
 * Build-time dispatch: prefetch dev PNG or decrypt secure payload once per session.
 * @returns {Promise<string>} resolved URL (dev webpack URL or secure blob URL)
 */
export const prefetchSupportQr = process.env.REACT_APP_SUPPORT_QR_SECURE === 'true'
  ? require('./supportQrSecure').prefetchSecureSupportQr
  : require('./supportQrDevAsset').prefetchDevSupportQr;

export const getCachedSupportQrUrl = process.env.REACT_APP_SUPPORT_QR_SECURE === 'true'
  ? require('./supportQrSecure').getCachedSecureSupportQrUrl
  : () => null;
