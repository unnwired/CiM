import { SUPPORT_QR_PAYLOAD } from '../support/supportQrPayload.generated';

export const SUPPORT_QR_SECURE_ENABLED = process.env.REACT_APP_SUPPORT_QR_SECURE === 'true';

// Must stay in sync with scripts/Generate-SupportQrPayload.ps1
const KEY_MATERIAL = 'CiM-SupportQr-v1';

function bytesToHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return bytesToHex(new Uint8Array(digest));
}

async function importAesKey() {
  const encoded = new TextEncoder().encode(KEY_MATERIAL);
  const hash = await crypto.subtle.digest('SHA-256', encoded);
  return crypto.subtle.importKey('raw', hash, { name: 'AES-CBC' }, false, ['decrypt']);
}

function base64ToBytes(b64) {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

function detectImageMime(bytes) {
  if (bytes.length >= 4
    && bytes[0] === 0x89
    && bytes[1] === 0x50
    && bytes[2] === 0x4e
    && bytes[3] === 0x47) {
    return 'image/png';
  }
  if (bytes.length >= 3
    && bytes[0] === 0xff
    && bytes[1] === 0xd8
    && bytes[2] === 0xff) {
    return 'image/jpeg';
  }
  return null;
}

/**
 * Decrypt export-time payload, verify SHA-256, return a PNG blob URL.
 * @returns {Promise<string>}
 */
export async function loadSecureSupportQrObjectUrl() {
  if (!SUPPORT_QR_PAYLOAD) {
    throw new Error('Support QR payload missing. Re-run export with frontend hardening.');
  }
  const { iv, ciphertext, sha256, mime: expectedMime } = SUPPORT_QR_PAYLOAD;
  if (!iv || !ciphertext || !sha256) {
    throw new Error('Support QR payload is incomplete.');
  }

  const key = await importAesKey();
  const plainBuffer = await crypto.subtle.decrypt(
    { name: 'AES-CBC', iv: base64ToBytes(iv) },
    key,
    base64ToBytes(ciphertext),
  );
  const plain = new Uint8Array(plainBuffer);

  const detectedMime = detectImageMime(plain);
  if (!detectedMime) {
    throw new Error('Support QR integrity check failed (invalid image data).');
  }
  if (expectedMime && detectedMime !== expectedMime) {
    throw new Error('Support QR integrity check failed (format mismatch).');
  }

  const actualHash = await sha256Hex(plain);
  if (actualHash !== String(sha256).toLowerCase()) {
    throw new Error('Support QR integrity check failed (hash mismatch).');
  }

  const blob = new Blob([plain], { type: detectedMime });
  return URL.createObjectURL(blob);
}
