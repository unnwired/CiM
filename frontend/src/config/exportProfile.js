/** True when built with `REACT_APP_EXPORT_MODE=distribution` (export_flowx.ps1 -Mode distribution). */
export const isDistributionProfile = process.env.REACT_APP_EXPORT_MODE === 'distribution';
