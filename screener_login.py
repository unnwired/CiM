"""
Log in to Screener.in and verify data is visible before saving session.
"""

import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import shutil

PROFILE_DIR  = Path(r"D:\Programs\NSE Pulse\Claude Ai\data\screener_profile")
SESSION_FILE = Path(r"D:\Programs\NSE Pulse\Claude Ai\data\screener_session.json")

async def login():
    # Clear old profile to start fresh
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
        print("✓ Cleared old profile")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ],
            ignore_default_args=["--enable-automation"],
            viewport=None,
        )

        page = context.pages[0] if context.pages else await context.new_page()

        print("\nOpening Screener.in...")
        await page.goto("https://www.screener.in/login/", timeout=30000)

        print("\nInstructions:")
        print("1. Log in with your Google account")
        print("2. After login, go to: https://www.screener.in/company/GRSE/consolidated/")
        print("3. Wait for the page to fully load — quarterly numbers should be visible")
        print("4. DO NOT close the browser")
        print("5. Come back here and press Enter\n")

        input("Press Enter ONLY after you can see quarterly numbers on the GRSE page...")

        # Verify data is actually there
        current_url = page.url
        print(f"\nCurrent URL: {current_url}")

        if "screener.in/company" not in current_url:
            print("Navigating to GRSE page...")
            await page.goto("https://www.screener.in/company/GRSE/consolidated/",
                          wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

        qt_html = await page.eval_on_selector("#quarters", "el => el.innerHTML")
        print(f"Quarters HTML length: {len(qt_html)}")

        # Check actual data values
        rows = await page.eval_on_selector_all(
            "#quarters tbody tr",
            """rows => rows.map(row => {
                const cells = row.querySelectorAll('td');
                return Array.from(cells).map(c => c.innerText.trim());
            })"""
        )
        print(f"First row cells: {rows[0] if rows else 'none'}")

        if rows and len(rows[0]) > 1:
            print("✓ Data confirmed visible")
            await context.storage_state(path=str(SESSION_FILE))
            cookies = await context.cookies()
            screener_cookies = [c for c in cookies if "screener" in c.get("domain","")]
            print(f"✓ {len(screener_cookies)} cookies saved")
            print(f"✓ Session saved to: {SESSION_FILE}")
        else:
            print("✗ Data not visible — please try again")
            print("Make sure you can see actual numbers in the quarterly table before pressing Enter")

        input("\nPress Enter to close the browser...")
        await context.close()

asyncio.run(login())
