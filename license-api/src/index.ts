import {
  decryptTotpSecret,
  encryptTotpSecret,
  hashPassword,
  hashToken,
  randomToken,
  recoveryCode,
  sha256Hex,
  signJwt,
  uuid,
  verifyJwt,
  verifyPassword,
} from './crypto';
import { type ClientEnv, isWebClientEnv, resolveClientEnv, type ClientEnvBody } from './clientEnv';
import { type ClientGeo, resolveClientGeo } from './clientGeo';
import {
  formatDenyReason,
  isBlockingEnabled,
  lookupIpReputation,
  reputationToDbFlags,
  type IpReputationDbFlags,
} from './ipReputation';
import { generateTotpSecret, otpauthUri, verifyTotp } from './totp';

export interface Env {
  DB: D1Database;
  JWT_SECRET: string;
  TOTP_ENCRYPTION_KEY: string;
  REFRESH_PEPPER: string;
  IPQS_API_KEY?: string;
  BLOCK_ANONYMIZED_NETWORKS?: string;
  IP_REPUTATION_STRICTNESS?: string;
  IP_REPUTATION_FAIL_CLOSED?: string;
  MAX_DEVICES?: string;
  ACCESS_TTL_MINUTES?: string;
  REFRESH_TTL_DAYS?: string;
  OFFLINE_GRACE_DAYS?: string;
}

type UserRow = {
  id: string;
  email: string;
  password_hash: string;
  status: string;
  totp_enabled: number;
  totp_secret_enc: string | null;
  plan?: string | null;
};

async function maxDevicesForUser(env: Env, userId: string): Promise<number> {
  try {
    const row = await env.DB.prepare('SELECT max_devices FROM user_limits WHERE user_id = ?')
      .bind(userId)
      .first<{ max_devices: number | null }>();
    if (row?.max_devices != null && Number.isFinite(row.max_devices)) {
      return row.max_devices;
    }
  } catch {
    // user_limits table not migrated yet
  }
  return intEnv(env, 'MAX_DEVICES', 2);
}

function planForUser(user: UserRow): string {
  const p = user.plan;
  return p && String(p).trim() ? String(p).trim() : 'free';
}

async function isDeviceRevoked(env: Env, userId: string, deviceId: string): Promise<boolean> {
  const row = await env.DB.prepare(
    'SELECT revoked FROM devices WHERE user_id = ? AND device_id = ?',
  )
    .bind(userId, deviceId)
    .first<{ revoked: number }>();
  return !row || !!row.revoked;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
  });
}

function err(message: string, status = 400, extra: Record<string, unknown> = {}): Response {
  return json({ detail: message, ...extra }, status);
}

function corsPreflight(): Response {
  return new Response(null, {
    status: 204,
    headers: {
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET, POST, OPTIONS',
      'access-control-allow-headers': 'content-type, authorization',
    },
  });
}

function intEnv(env: Env, key: keyof Env, fallback: number): number {
  const raw = env[key];
  const n = parseInt(String(raw ?? ''), 10);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeEmail(email: string): string {
  return String(email || '').trim().toLowerCase();
}

function validatePassword(password: string): string | null {
  if (password.length < 8) return 'Password must be at least 8 characters';
  return null;
}

async function readJson<T>(request: Request): Promise<T> {
  return (await request.json()) as T;
}

async function bearerUser(request: Request, env: Env): Promise<{ user: UserRow; payload: Record<string, unknown> } | null> {
  const auth = request.headers.get('authorization') || '';
  const m = auth.match(/^Bearer\s+(.+)$/i);
  if (!m) return null;
  const payload = await verifyJwt(m[1], env.JWT_SECRET);
  if (!payload || typeof payload.sub !== 'string') return null;
  const user = await env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(payload.sub).first<UserRow>();
  if (!user || user.status !== 'active') return null;
  return { user, payload };
}

async function issueTokens(
  env: Env,
  user: UserRow,
  deviceId: string,
): Promise<{ access_token: string; refresh_token: string; expires_in: number; offline_grace_days: number }> {
  const accessTtl = intEnv(env, 'ACCESS_TTL_MINUTES', 60) * 60;
  const refreshDays = intEnv(env, 'REFRESH_TTL_DAYS', 90);
  const graceDays = intEnv(env, 'OFFLINE_GRACE_DAYS', 7);
  const access_token = await signJwt(
    { sub: user.id, email: user.email, device_id: deviceId, plan: planForUser(user) },
    env.JWT_SECRET,
    accessTtl,
  );
  const refresh_token = randomToken(32);
  const refreshHash = await hashToken(refresh_token, env.REFRESH_PEPPER);
  const expiresAt = new Date(Date.now() + refreshDays * 86400_000).toISOString();
  await env.DB.prepare(
    'INSERT INTO refresh_tokens (id, user_id, device_id, token_hash, expires_at) VALUES (?, ?, ?, ?, ?)',
  )
    .bind(uuid(), user.id, deviceId, refreshHash, expiresAt)
    .run();
  return { access_token, refresh_token, expires_in: accessTtl, offline_grace_days: graceDays };
}

async function recordLoginEvent(
  env: Env,
  userId: string,
  deviceId: string,
  appVersion: string,
  geo: ClientGeo,
  clientEnv: ClientEnv,
  rep: IpReputationDbFlags,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO login_events (
       id, user_id, device_id, ip, country, city, region, app_version,
       client_platform, client_os, client_os_version, client_browser, client_browser_version, client_device_type,
       ip_proxy, ip_vpn, ip_tor, ip_datacenter, ip_fraud_score
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      uuid(),
      userId,
      deviceId,
      geo.ip,
      geo.country,
      geo.city,
      geo.region,
      appVersion,
      clientEnv.client_platform,
      clientEnv.client_os,
      clientEnv.client_os_version,
      clientEnv.client_browser,
      clientEnv.client_browser_version,
      clientEnv.client_device_type,
      rep.ip_proxy,
      rep.ip_vpn,
      rep.ip_tor,
      rep.ip_datacenter,
      rep.ip_fraud_score,
    )
    .run();
}

async function recordLoginDenied(
  env: Env,
  userId: string,
  email: string,
  deviceId: string,
  geo: ClientGeo,
  denyReason: string,
  rep: IpReputationDbFlags,
): Promise<void> {
  try {
    await env.DB.prepare(
      `INSERT INTO login_denied_events (
         id, user_id, email, device_id, ip, country, city, region, deny_reason,
         ip_proxy, ip_vpn, ip_tor, ip_datacenter, ip_fraud_score
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        uuid(),
        userId,
        email,
        deviceId,
        geo.ip,
        geo.country,
        geo.city,
        geo.region,
        denyReason,
        rep.ip_proxy,
        rep.ip_vpn,
        rep.ip_tor,
        rep.ip_datacenter,
        rep.ip_fraud_score,
      )
      .run();
  } catch {
    // login_denied_events table not migrated yet
  }
}

async function syncDeviceReputation(
  env: Env,
  userId: string,
  deviceId: string,
  rep: IpReputationDbFlags,
): Promise<void> {
  try {
    await env.DB.prepare(
      `UPDATE devices SET last_ip_proxy = ?, last_ip_vpn = ?, last_ip_tor = ?,
       last_ip_datacenter = ?, last_ip_fraud_score = ?
       WHERE user_id = ? AND device_id = ?`,
    )
      .bind(rep.ip_proxy, rep.ip_vpn, rep.ip_tor, rep.ip_datacenter, rep.ip_fraud_score, userId, deviceId)
      .run();
  } catch {
    // reputation columns not migrated yet
  }
}

async function registerDevice(
  env: Env,
  userId: string,
  deviceId: string,
  deviceName: string,
  appVersion: string,
  geo: ClientGeo,
  clientEnv: ClientEnv,
): Promise<Response | null> {
  const maxDevices = await maxDevicesForUser(env, userId);
  const existing = await env.DB.prepare(
    'SELECT id FROM devices WHERE user_id = ? AND device_id = ? AND revoked = 0',
  )
    .bind(userId, deviceId)
    .first<{ id: string }>();
  const webClient = isWebClientEnv(clientEnv);
  if (existing) {
    if (webClient) {
      await env.DB.prepare(
        `UPDATE devices SET last_seen = datetime('now'), device_name = ?, app_version = ?,
         last_ip = ?, last_country = ?, last_city = ?, last_region = ?,
         last_client_platform = ?, last_client_os = ?, last_client_os_version = ?,
         last_client_browser = ?, last_client_browser_version = ?, last_client_device_type = ?
         WHERE id = ?`,
      )
        .bind(
          deviceName,
          appVersion,
          geo.ip,
          geo.country,
          geo.city,
          geo.region,
          clientEnv.client_platform,
          clientEnv.client_os,
          clientEnv.client_os_version,
          clientEnv.client_browser,
          clientEnv.client_browser_version,
          clientEnv.client_device_type,
          existing.id,
        )
        .run();
    } else {
      await env.DB.prepare(
        `UPDATE devices SET last_seen = datetime('now'), device_name = ?, app_version = ?,
         last_ip = ?, last_country = ?, last_city = ?, last_region = ?
         WHERE id = ?`,
      )
        .bind(deviceName, appVersion, geo.ip, geo.country, geo.city, geo.region, existing.id)
        .run();
    }
    return null;
  }
  const countRow = await env.DB.prepare(
    'SELECT COUNT(*) AS c FROM devices WHERE user_id = ? AND revoked = 0',
  )
    .bind(userId)
    .first<{ c: number }>();
  if ((countRow?.c ?? 0) >= maxDevices) {
    return err(`Device limit reached (${maxDevices} PCs per account)`, 403, { max_devices: maxDevices });
  }
  if (webClient) {
    await env.DB.prepare(
      `INSERT INTO devices (
         id, user_id, device_id, device_name, app_version,
         last_ip, last_country, last_city, last_region,
         last_client_platform, last_client_os, last_client_os_version,
         last_client_browser, last_client_browser_version, last_client_device_type
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        uuid(),
        userId,
        deviceId,
        deviceName,
        appVersion,
        geo.ip,
        geo.country,
        geo.city,
        geo.region,
        clientEnv.client_platform,
        clientEnv.client_os,
        clientEnv.client_os_version,
        clientEnv.client_browser,
        clientEnv.client_browser_version,
        clientEnv.client_device_type,
      )
      .run();
  } else {
    await env.DB.prepare(
      `INSERT INTO devices (id, user_id, device_id, device_name, app_version, last_ip, last_country, last_city, last_region)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(uuid(), userId, deviceId, deviceName, appVersion, geo.ip, geo.country, geo.city, geo.region)
      .run();
  }
  return null;
}

async function handleSignup(request: Request, env: Env): Promise<Response> {
  const body = await readJson<{ email?: string; password?: string }>(request);
  const email = normalizeEmail(body.email || '');
  const password = String(body.password || '');
  if (!email || !email.includes('@')) return err('Valid email required');
  const pwErr = validatePassword(password);
  if (pwErr) return err(pwErr);
  const exists = await env.DB.prepare('SELECT id FROM users WHERE email = ?').bind(email).first();
  if (exists) return err('Email already registered', 409);
  const userId = uuid();
  const password_hash = await hashPassword(password);
  await env.DB.prepare(
    'INSERT INTO users (id, email, password_hash, status) VALUES (?, ?, ?, ?)',
  )
    .bind(userId, email, password_hash, 'active')
    .run();
  const codes: string[] = [];
  for (let i = 0; i < 10; i++) {
    const code = recoveryCode();
    codes.push(code);
    const code_hash = await sha256Hex(code.replace(/-/g, '').toUpperCase());
    await env.DB.prepare(
      'INSERT INTO recovery_codes (id, user_id, code_hash) VALUES (?, ?, ?)',
    )
      .bind(uuid(), userId, code_hash)
      .run();
  }
  return json(
    { user_id: userId, email, recovery_codes: codes, message: 'Save recovery codes — shown once' },
    201,
  );
}

async function handleLogin(request: Request, env: Env): Promise<Response> {
  const body = await readJson<{
    email?: string;
    password?: string;
    totp_code?: string;
    device_id?: string;
    device_name?: string;
    app_version?: string;
    client_ip?: string;
    client_country?: string;
    client_city?: string;
    client_region?: string;
  } & ClientEnvBody>(request);
  const email = normalizeEmail(body.email || '');
  const password = String(body.password || '');
  const deviceId = String(body.device_id || '').trim().toUpperCase();
  const deviceName = String(body.device_name || 'Unknown PC').slice(0, 120);
  const appVersion = String(body.app_version || '').slice(0, 40);
  const geo = resolveClientGeo(request, body);
  const clientEnv = resolveClientEnv(body);
  if (!email || !password || !deviceId) return err('email, password, and device_id required');
  const user = await env.DB.prepare('SELECT * FROM users WHERE email = ?').bind(email).first<UserRow>();
  if (!user || user.status !== 'active') return err('Invalid email or password', 401);
  if (!(await verifyPassword(password, user.password_hash))) return err('Invalid email or password', 401);
  if (user.totp_enabled) {
    const totp = String(body.totp_code || '');
    if (!totp) return err('TOTP code required', 401, { need_totp: true });
    const secret = user.totp_secret_enc
      ? await decryptTotpSecret(user.totp_secret_enc, env.TOTP_ENCRYPTION_KEY)
      : '';
    if (!secret || !(await verifyTotp(secret, totp))) return err('Invalid TOTP code', 401);
  }
  const reputation = await lookupIpReputation(geo.ip, env);
  const repFlags = reputationToDbFlags(reputation);
  if (isBlockingEnabled(env) && reputation.shouldBlock) {
    await recordLoginDenied(
      env,
      user.id,
      email,
      deviceId,
      geo,
      formatDenyReason(reputation),
      repFlags,
    );
    return err('Sign-in is not allowed from VPN, proxy, Tor, or datacenter networks.', 403, {
      network_blocked: true,
    });
  }
  const deviceErr = await registerDevice(env, user.id, deviceId, deviceName, appVersion, geo, clientEnv);
  if (deviceErr) return deviceErr;
  await syncDeviceReputation(env, user.id, deviceId, repFlags);
  await recordLoginEvent(env, user.id, deviceId, appVersion, geo, clientEnv, repFlags);
  const tokens = await issueTokens(env, user, deviceId);
  const devicesRow = await env.DB.prepare(
    'SELECT COUNT(*) AS c FROM devices WHERE user_id = ? AND revoked = 0',
  )
    .bind(user.id)
    .first<{ c: number }>();
  const maxDev = await maxDevicesForUser(env, user.id);
  return json({
    ...tokens,
    email: user.email,
    plan: planForUser(user),
    totp_enabled: !!user.totp_enabled,
    devices_used: devicesRow?.c ?? 1,
    max_devices: maxDev,
  });
}

async function handleRefresh(request: Request, env: Env): Promise<Response> {
  const body = await readJson<{ refresh_token?: string; device_id?: string }>(request);
  const refreshToken = String(body.refresh_token || '');
  const deviceId = String(body.device_id || '').trim().toUpperCase();
  if (!refreshToken || !deviceId) return err('refresh_token and device_id required');
  const tokenHash = await hashToken(refreshToken, env.REFRESH_PEPPER);
  const row = await env.DB.prepare(
    `SELECT rt.id AS rt_id, rt.user_id, u.email, u.status, u.totp_enabled
     FROM refresh_tokens rt JOIN users u ON u.id = rt.user_id
     WHERE rt.token_hash = ? AND rt.device_id = ? AND rt.revoked_at IS NULL AND rt.expires_at > datetime('now')`,
  )
    .bind(tokenHash, deviceId)
    .first<{ rt_id: string; user_id: string; email: string; status: string; totp_enabled: number }>();
  if (!row || row.status !== 'active') return err('Invalid refresh token', 401);
  if (await isDeviceRevoked(env, row.user_id, deviceId)) {
    return err('Device disabled', 403);
  }
  await env.DB.prepare('UPDATE refresh_tokens SET revoked_at = datetime(\'now\') WHERE id = ?').bind(row.rt_id).run();
  const user = await env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(row.user_id).first<UserRow>();
  if (!user) return err('Invalid refresh token', 401);
  const tokens = await issueTokens(env, user, deviceId);
  return json({ ...tokens, email: user.email, plan: planForUser(user) });
}

async function handleLogout(request: Request, env: Env): Promise<Response> {
  const body = await readJson<{ refresh_token?: string }>(request);
  const refreshToken = String(body.refresh_token || '');
  if (!refreshToken) return err('refresh_token required');
  const tokenHash = await hashToken(refreshToken, env.REFRESH_PEPPER);
  await env.DB.prepare(
    'UPDATE refresh_tokens SET revoked_at = datetime(\'now\') WHERE token_hash = ? AND revoked_at IS NULL',
  )
    .bind(tokenHash)
    .run();
  return json({ status: 'ok' });
}

async function handleResetRecovery(request: Request, env: Env): Promise<Response> {
  const body = await readJson<{ email?: string; recovery_code?: string; new_password?: string }>(request);
  const email = normalizeEmail(body.email || '');
  const code = String(body.recovery_code || '').replace(/\s/g, '').toUpperCase();
  const newPassword = String(body.new_password || '');
  const pwErr = validatePassword(newPassword);
  if (pwErr) return err(pwErr);
  if (!email || !code) return err('email and recovery_code required');
  const user = await env.DB.prepare('SELECT * FROM users WHERE email = ?').bind(email).first<UserRow>();
  if (!user) return json({ status: 'ok', message: 'If the account exists, password was reset' });
  const codeHash = await sha256Hex(code.replace(/-/g, ''));
  const rc = await env.DB.prepare(
    'SELECT id FROM recovery_codes WHERE user_id = ? AND code_hash = ? AND used_at IS NULL',
  )
    .bind(user.id, codeHash)
    .first<{ id: string }>();
  if (!rc) return err('Invalid recovery code', 400);
  await env.DB.prepare('UPDATE recovery_codes SET used_at = datetime(\'now\') WHERE id = ?').bind(rc.id).run();
  const password_hash = await hashPassword(newPassword);
  await env.DB.prepare('UPDATE users SET password_hash = ? WHERE id = ?').bind(password_hash, user.id).run();
  await env.DB.prepare('UPDATE refresh_tokens SET revoked_at = datetime(\'now\') WHERE user_id = ? AND revoked_at IS NULL')
    .bind(user.id)
    .run();
  return json({ status: 'ok', message: 'Password reset — sign in again on each device' });
}

async function handleLicenseStatus(request: Request, env: Env): Promise<Response> {
  const auth = await bearerUser(request, env);
  if (!auth) return err('Unauthorized', 401);
  const { user, payload } = auth;
  const deviceId = String(payload.device_id || '');
  if (deviceId && (await isDeviceRevoked(env, user.id, deviceId))) {
    return err('Device disabled', 403);
  }
  const devicesRow = await env.DB.prepare(
    'SELECT COUNT(*) AS c FROM devices WHERE user_id = ? AND revoked = 0',
  )
    .bind(user.id)
    .first<{ c: number }>();
  const maxDev = await maxDevicesForUser(env, user.id);
  return json({
    valid: true,
    email: user.email,
    plan: planForUser(user),
    totp_enabled: !!user.totp_enabled,
    devices_used: devicesRow?.c ?? 0,
    max_devices: maxDev,
    offline_grace_days: intEnv(env, 'OFFLINE_GRACE_DAYS', 7),
    device_id: deviceId,
  });
}

async function handleHeartbeat(request: Request, env: Env): Promise<Response> {
  const auth = await bearerUser(request, env);
  if (!auth) return err('Unauthorized', 401);
  const deviceId = String(auth.payload.device_id || '');
  let geo: ClientGeo = resolveClientGeo(request);
  let clientEnv: ClientEnv = resolveClientEnv();
  try {
    const body = await readJson<{
      client_ip?: string;
      client_country?: string;
      client_city?: string;
      client_region?: string;
    } & ClientEnvBody>(request);
    geo = resolveClientGeo(request, body);
    clientEnv = resolveClientEnv(body);
  } catch {
    // empty or non-JSON body — use connecting IP only
  }
  if (isWebClientEnv(clientEnv)) {
    await env.DB.prepare(
      `UPDATE devices SET last_seen = datetime('now'),
       last_ip = COALESCE(?, last_ip), last_country = COALESCE(?, last_country),
       last_city = COALESCE(?, last_city), last_region = COALESCE(?, last_region),
       last_client_platform = COALESCE(?, last_client_platform),
       last_client_os = COALESCE(?, last_client_os),
       last_client_os_version = COALESCE(?, last_client_os_version),
       last_client_browser = COALESCE(?, last_client_browser),
       last_client_browser_version = COALESCE(?, last_client_browser_version),
       last_client_device_type = COALESCE(?, last_client_device_type)
       WHERE user_id = ? AND device_id = ? AND revoked = 0`,
    )
      .bind(
        geo.ip,
        geo.country,
        geo.city,
        geo.region,
        clientEnv.client_platform,
        clientEnv.client_os,
        clientEnv.client_os_version,
        clientEnv.client_browser,
        clientEnv.client_browser_version,
        clientEnv.client_device_type,
        auth.user.id,
        deviceId,
      )
      .run();
  } else {
    await env.DB.prepare(
      `UPDATE devices SET last_seen = datetime('now'),
       last_ip = COALESCE(?, last_ip), last_country = COALESCE(?, last_country),
       last_city = COALESCE(?, last_city), last_region = COALESCE(?, last_region)
       WHERE user_id = ? AND device_id = ? AND revoked = 0`,
    )
      .bind(geo.ip, geo.country, geo.city, geo.region, auth.user.id, deviceId)
      .run();
  }
  return json({
    valid: true,
    server_time: new Date().toISOString(),
    offline_grace_days: intEnv(env, 'OFFLINE_GRACE_DAYS', 7),
  });
}

async function handleTotpEnroll(request: Request, env: Env): Promise<Response> {
  const auth = await bearerUser(request, env);
  if (!auth) return err('Unauthorized', 401);
  if (auth.user.totp_enabled) return err('TOTP already enabled');
  const secret = generateTotpSecret();
  const pendingEnc = await encryptTotpSecret(secret, env.TOTP_ENCRYPTION_KEY);
  await env.DB.prepare('UPDATE users SET totp_secret_enc = ? WHERE id = ? AND totp_enabled = 0')
    .bind(pendingEnc, auth.user.id)
    .run();
  return json({
    otpauth_uri: otpauthUri(auth.user.email, secret),
    secret_base32: secret,
    message: 'Scan QR then confirm with a 6-digit code',
  });
}

async function handleTotpConfirm(request: Request, env: Env): Promise<Response> {
  const auth = await bearerUser(request, env);
  if (!auth) return err('Unauthorized', 401);
  const body = await readJson<{ code?: string }>(request);
  const code = String(body.code || '');
  if (!auth.user.totp_secret_enc) return err('Enroll TOTP first');
  const secret = await decryptTotpSecret(auth.user.totp_secret_enc, env.TOTP_ENCRYPTION_KEY);
  if (!(await verifyTotp(secret, code))) return err('Invalid TOTP code');
  await env.DB.prepare('UPDATE users SET totp_enabled = 1 WHERE id = ?').bind(auth.user.id).run();
  return json({ status: 'ok', totp_enabled: true });
}

async function handleTotpDisable(request: Request, env: Env): Promise<Response> {
  const auth = await bearerUser(request, env);
  if (!auth) return err('Unauthorized', 401);
  const body = await readJson<{ password?: string; totp_code?: string }>(request);
  if (!(await verifyPassword(String(body.password || ''), auth.user.password_hash))) {
    return err('Invalid password', 401);
  }
  if (auth.user.totp_enabled) {
    const secret = auth.user.totp_secret_enc
      ? await decryptTotpSecret(auth.user.totp_secret_enc, env.TOTP_ENCRYPTION_KEY)
      : '';
    if (!secret || !(await verifyTotp(secret, String(body.totp_code || '')))) {
      return err('Invalid TOTP code', 401);
    }
  }
  await env.DB.prepare('UPDATE users SET totp_enabled = 0, totp_secret_enc = NULL WHERE id = ?')
    .bind(auth.user.id)
    .run();
  return json({ status: 'ok', totp_enabled: false });
}

async function handleRecoveryRegenerate(request: Request, env: Env): Promise<Response> {
  const auth = await bearerUser(request, env);
  if (!auth) return err('Unauthorized', 401);
  const body = await readJson<{ password?: string; totp_code?: string }>(request);
  if (!(await verifyPassword(String(body.password || ''), auth.user.password_hash))) {
    return err('Invalid password', 401);
  }
  if (auth.user.totp_enabled) {
    const secret = auth.user.totp_secret_enc
      ? await decryptTotpSecret(auth.user.totp_secret_enc, env.TOTP_ENCRYPTION_KEY)
      : '';
    if (!secret || !(await verifyTotp(secret, String(body.totp_code || '')))) {
      return err('Invalid TOTP code', 401);
    }
  }
  await env.DB.prepare('DELETE FROM recovery_codes WHERE user_id = ?').bind(auth.user.id).run();
  const codes: string[] = [];
  for (let i = 0; i < 10; i++) {
    const code = recoveryCode();
    codes.push(code);
    const code_hash = await sha256Hex(code.replace(/-/g, '').toUpperCase());
    await env.DB.prepare('INSERT INTO recovery_codes (id, user_id, code_hash) VALUES (?, ?, ?)')
      .bind(uuid(), auth.user.id, code_hash)
      .run();
  }
  return json({ recovery_codes: codes, message: 'Save these codes — shown once' });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') return corsPreflight();
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    try {
      if (request.method === 'GET' && path === '/health') {
        return json({ status: 'ok', service: 'chartsinmotion-license' });
      }
      if (request.method === 'POST' && path === '/auth/signup') return handleSignup(request, env);
      if (request.method === 'POST' && path === '/auth/login') return handleLogin(request, env);
      if (request.method === 'POST' && path === '/auth/refresh') return handleRefresh(request, env);
      if (request.method === 'POST' && path === '/auth/logout') return handleLogout(request, env);
      if (request.method === 'POST' && path === '/auth/reset-with-recovery-code') {
        return handleResetRecovery(request, env);
      }
      if (request.method === 'GET' && path === '/license/status') return handleLicenseStatus(request, env);
      if (request.method === 'POST' && path === '/license/heartbeat') return handleHeartbeat(request, env);
      if (request.method === 'POST' && path === '/auth/totp/enroll') return handleTotpEnroll(request, env);
      if (request.method === 'POST' && path === '/auth/totp/confirm') return handleTotpConfirm(request, env);
      if (request.method === 'POST' && path === '/auth/totp/disable') return handleTotpDisable(request, env);
      if (request.method === 'POST' && path === '/auth/recovery/regenerate') {
        return handleRecoveryRegenerate(request, env);
      }
      return err('Not found', 404);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Internal error';
      return err(message, 500);
    }
  },
};
