/* eslint-disable global-require */

const SupportQrModalBody = process.env.REACT_APP_SUPPORT_QR_SECURE === 'true'
  ? require('./SupportQrModalBody.secure').default
  : require('./SupportQrModalBody.dev').default;

export default SupportQrModalBody;
