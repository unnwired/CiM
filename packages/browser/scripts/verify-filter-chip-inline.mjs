/**
 * One filter chip = one pill, inline remove always visible (no ghost corner ×).
 * Run: node scripts/verify-filter-chip-inline.mjs
 */
import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(__dirname, '../src/index.css'), 'utf8');

const HTML = `
<style>${css}</style>
<div class="dashboard-filter-chips-rail" style="display:flex;padding:16px">
  <div class="dashboard-filter-chip">
    <div class="dashboard-filter-chip-body" style="border:1px solid #388bfd">
      <span class="dashboard-filter-chip-label" style="color:#388bfd">EMA 20 (1D) &gt; EMA 50</span>
      <button type="button" class="dashboard-filter-chip-toggle"><span style="width:8px;height:8px;border-radius:999px;background:#388bfd;display:block"></span></button>
      <button type="button" class="dashboard-filter-chip-remove" aria-label="Remove filter">
        <svg width="6" height="6" viewBox="0 0 10 10" fill="none"><path d="M2 2L8 8M8 2L2 8" stroke="currentColor" stroke-width="1.6"/></svg>
      </button>
    </div>
  </div>
</div>
`;

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setContent(HTML);

  const chips = await page.locator('.dashboard-filter-chip').count();
  const bodies = await page.locator('.dashboard-filter-chip-body').count();
  const removes = await page.locator('.dashboard-filter-chip-remove').count();
  const closes = await page.locator('.dashboard-filter-chip-close').count();

  if (chips !== 1 || bodies !== 1 || removes !== 1 || closes !== 0) {
    throw new Error(`expected 1 chip/body/remove, 0 corner close; got chips=${chips} bodies=${bodies} remove=${removes} close=${closes}`);
  }

  const opacity = await page.locator('.dashboard-filter-chip-remove').evaluate((el) => getComputedStyle(el).opacity);
  if (opacity !== '1') throw new Error(`remove must always be visible, opacity=${opacity}`);

  const remove = page.locator('.dashboard-filter-chip-remove');
  await remove.hover();
  const color = await remove.evaluate((el) => getComputedStyle(el).color);
  // accent-red should apply on hover (browser computes to rgb)
  if (!color.includes('248') && !color.includes('f8')) {
    throw new Error(`remove should turn red on hover, color=${color}`);
  }

  console.log('OK: single chip, inline remove always visible, red on hover');
  await browser.close();
}

main().catch((e) => {
  console.error('FAIL:', e.message || e);
  process.exit(1);
});
