import axios from 'axios';

const API = '';

export async function fetchLicenseStatus() {
  const { data } = await axios.get(`${API}/api/license/status`);
  return data;
}

export async function totpEnroll() {
  const { data } = await axios.post(`${API}/api/auth/totp/enroll`);
  return data;
}

export async function totpConfirm(code) {
  const { data } = await axios.post(`${API}/api/auth/totp/confirm`, { code });
  return data;
}

export async function totpDisable(password, totp_code) {
  const { data } = await axios.post(`${API}/api/auth/totp/disable`, { password, totp_code });
  return data;
}

export async function recoveryRegenerate(password, totp_code) {
  const { data } = await axios.post(`${API}/api/auth/recovery/regenerate`, { password, totp_code: totp_code || undefined });
  return data;
}

export async function logout() {
  const { data } = await axios.post(`${API}/api/auth/logout`);
  return data;
}

export async function licenseHeartbeat() {
  const { data } = await axios.post(`${API}/api/license/heartbeat`);
  return data;
}
