CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  totp_enabled INTEGER NOT NULL DEFAULT 0,
  totp_secret_enc TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  device_name TEXT,
  app_version TEXT,
  first_seen TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen TEXT NOT NULL DEFAULT (datetime('now')),
  revoked INTEGER NOT NULL DEFAULT 0,
  last_ip TEXT,
  last_country TEXT,
  last_city TEXT,
  last_region TEXT,
  last_client_platform TEXT,
  last_client_os TEXT,
  last_client_os_version TEXT,
  last_client_browser TEXT,
  last_client_browser_version TEXT,
  last_client_device_type TEXT,
  last_ip_proxy INTEGER NOT NULL DEFAULT 0,
  last_ip_vpn INTEGER NOT NULL DEFAULT 0,
  last_ip_tor INTEGER NOT NULL DEFAULT 0,
  last_ip_datacenter INTEGER NOT NULL DEFAULT 0,
  last_ip_fraud_score INTEGER,
  UNIQUE(user_id, device_id)
);

CREATE TABLE IF NOT EXISTS login_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  ip TEXT,
  country TEXT,
  city TEXT,
  region TEXT,
  app_version TEXT,
  client_platform TEXT,
  client_os TEXT,
  client_os_version TEXT,
  client_browser TEXT,
  client_browser_version TEXT,
  client_device_type TEXT,
  ip_proxy INTEGER NOT NULL DEFAULT 0,
  ip_vpn INTEGER NOT NULL DEFAULT 0,
  ip_tor INTEGER NOT NULL DEFAULT 0,
  ip_datacenter INTEGER NOT NULL DEFAULT 0,
  ip_fraud_score INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS login_denied_events (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  email TEXT NOT NULL,
  device_id TEXT,
  ip TEXT,
  country TEXT,
  city TEXT,
  region TEXT,
  deny_reason TEXT NOT NULL,
  ip_proxy INTEGER NOT NULL DEFAULT 0,
  ip_vpn INTEGER NOT NULL DEFAULT 0,
  ip_tor INTEGER NOT NULL DEFAULT 0,
  ip_datacenter INTEGER NOT NULL DEFAULT 0,
  ip_fraud_score INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS recovery_codes (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_login_denied_created ON login_denied_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_denied_email ON login_denied_events(email);
CREATE INDEX IF NOT EXISTS idx_devices_user ON devices(user_id);
CREATE INDEX IF NOT EXISTS idx_login_events_created ON login_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_events_user ON login_events(user_id);
CREATE INDEX IF NOT EXISTS idx_login_events_device ON login_events(device_id);
CREATE INDEX IF NOT EXISTS idx_refresh_user_device ON refresh_tokens(user_id, device_id);
CREATE INDEX IF NOT EXISTS idx_recovery_user ON recovery_codes(user_id);
