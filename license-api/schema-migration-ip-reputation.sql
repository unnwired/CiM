-- IP reputation flags (IPQualityScore) on successful logins and devices
ALTER TABLE login_events ADD COLUMN ip_proxy INTEGER NOT NULL DEFAULT 0;
ALTER TABLE login_events ADD COLUMN ip_vpn INTEGER NOT NULL DEFAULT 0;
ALTER TABLE login_events ADD COLUMN ip_tor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE login_events ADD COLUMN ip_datacenter INTEGER NOT NULL DEFAULT 0;
ALTER TABLE login_events ADD COLUMN ip_fraud_score INTEGER;

ALTER TABLE devices ADD COLUMN last_ip_proxy INTEGER NOT NULL DEFAULT 0;
ALTER TABLE devices ADD COLUMN last_ip_vpn INTEGER NOT NULL DEFAULT 0;
ALTER TABLE devices ADD COLUMN last_ip_tor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE devices ADD COLUMN last_ip_datacenter INTEGER NOT NULL DEFAULT 0;
ALTER TABLE devices ADD COLUMN last_ip_fraud_score INTEGER;

-- Blocked sign-in attempts (VPN / proxy / Tor / datacenter)
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

CREATE INDEX IF NOT EXISTS idx_login_denied_created ON login_denied_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_denied_email ON login_denied_events(email);
