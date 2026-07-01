import axios from 'axios';
import { isDistributionProfile } from '../config/exportProfile';

/** Shared axios for distribution / web showcase (sends per-install session cookie on every request). */
export const api = axios.create({
  baseURL: '',
  timeout: isDistributionProfile ? 120000 : 30000,
  withCredentials: isDistributionProfile,
});

if (isDistributionProfile) {
  axios.defaults.withCredentials = true;
}

export default api;
