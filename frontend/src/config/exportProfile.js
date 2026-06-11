/** True when built with `REACT_APP_EXPORT_MODE=distribution` (export_cim.ps1 -Mode distribution). */
export const isDistributionProfile = process.env.REACT_APP_EXPORT_MODE === 'distribution';

/**
 * Dev-repo Account preview (mock user + simulated 2FA actions).
 * True for any non-distribution frontend build — including start_cim.bat's npm run build
 * (production NODE_ENV but no REACT_APP_EXPORT_MODE). False for exported client installs.
 */
export const isDevAccountPreview = !isDistributionProfile;

/** Mock license payload for dev Account preview (distribution uses live /api/license/status). */
export const DEV_ACCOUNT_PREVIEW = {
  mode: 'online',
  valid: true,
  email: 'preview@chartsinmotion.dev',
  plan: 'free',
  offline_cached: false,
  offline_grace_until: '2026-12-31T23:59:59',
};
