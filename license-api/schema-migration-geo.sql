-- Geo / login tracking (run once on cim-license D1)
ALTER TABLE devices ADD COLUMN last_ip TEXT;
ALTER TABLE devices ADD COLUMN last_country TEXT;
ALTER TABLE devices ADD COLUMN last_city TEXT;
ALTER TABLE devices ADD COLUMN last_region TEXT;

CREATE TABLE IF NOT EXISTS login_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  ip TEXT,
  country TEXT,
  city TEXT,
  region TEXT,
  app_version TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_login_events_created ON login_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_events_user ON login_events(user_id);
CREATE INDEX IF NOT EXISTS idx_login_events_device ON login_events(device_id);
