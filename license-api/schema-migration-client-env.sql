-- Web client OS / browser tracking (run once on cim-license D1)
ALTER TABLE devices ADD COLUMN last_client_platform TEXT;
ALTER TABLE devices ADD COLUMN last_client_os TEXT;
ALTER TABLE devices ADD COLUMN last_client_os_version TEXT;
ALTER TABLE devices ADD COLUMN last_client_browser TEXT;
ALTER TABLE devices ADD COLUMN last_client_browser_version TEXT;
ALTER TABLE devices ADD COLUMN last_client_device_type TEXT;

ALTER TABLE login_events ADD COLUMN client_platform TEXT;
ALTER TABLE login_events ADD COLUMN client_os TEXT;
ALTER TABLE login_events ADD COLUMN client_os_version TEXT;
ALTER TABLE login_events ADD COLUMN client_browser TEXT;
ALTER TABLE login_events ADD COLUMN client_browser_version TEXT;
ALTER TABLE login_events ADD COLUMN client_device_type TEXT;
