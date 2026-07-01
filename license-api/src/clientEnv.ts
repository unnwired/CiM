export type ClientEnv = {
  client_platform: string | null;
  client_os: string | null;
  client_os_version: string | null;
  client_browser: string | null;
  client_browser_version: string | null;
  client_device_type: string | null;
};

export type ClientEnvBody = {
  client_platform?: string;
  client_os?: string;
  client_os_version?: string;
  client_browser?: string;
  client_browser_version?: string;
  client_device_type?: string;
};

const EMPTY_CLIENT_ENV: ClientEnv = {
  client_platform: null,
  client_os: null,
  client_os_version: null,
  client_browser: null,
  client_browser_version: null,
  client_device_type: null,
};

function sanitizeField(raw: string | null | undefined, max: number): string | null {
  if (!raw) return null;
  const s = String(raw).trim().slice(0, max);
  return s || null;
}

export function resolveClientEnv(body?: ClientEnvBody): ClientEnv {
  const platform = sanitizeField(body?.client_platform, 16);
  if (platform !== 'web') return { ...EMPTY_CLIENT_ENV };
  return {
    client_platform: 'web',
    client_os: sanitizeField(body?.client_os, 40),
    client_os_version: sanitizeField(body?.client_os_version, 40),
    client_browser: sanitizeField(body?.client_browser, 40),
    client_browser_version: sanitizeField(body?.client_browser_version, 20),
    client_device_type: sanitizeField(body?.client_device_type, 16),
  };
}

export function isWebClientEnv(env: ClientEnv): boolean {
  return env.client_platform === 'web';
}
