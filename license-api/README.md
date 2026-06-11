# Charts In Motion — Online License API

Cloudflare Worker + D1 at **`https://chartsinmotion.chartsinmotion.workers.dev`**.

## One-time setup (vendor)

```bash
cd license-api
npm install
npx wrangler login
npx wrangler d1 create cim-license
```

Copy `database_id` from output into `wrangler.toml` (`REPLACE_AFTER_D1_CREATE`).

```bash
npx wrangler d1 execute cim-license --remote --file=./schema.sql
npx wrangler secret put JWT_SECRET
npx wrangler secret put TOTP_ENCRYPTION_KEY
npx wrangler secret put REFRESH_PEPPER
npx wrangler deploy
curl https://chartsinmotion.chartsinmotion.workers.dev/health
```

## Verify from repo

```powershell
.\scripts\Verify-CiMOnlineLicense.ps1 -LicenseApiUrl "https://chartsinmotion.chartsinmotion.workers.dev"
```

## Client config

[`config/product.json`](../config/product.json) → `licenseApiUrl`
