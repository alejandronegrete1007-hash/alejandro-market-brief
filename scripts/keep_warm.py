"""Wake the Streamlit app and warm its caches by visiting every page.

Run by .github/workflows/keep-warm.yml. A plain HTTP request is not enough:
Streamlit only runs the script (and fills st.cache_data) when a browser opens
a websocket session, so this uses a headless Chromium.
"""
import os
import sys
import time

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

BASE = os.environ.get("APP_URL", "https://alejandro-market-brief.streamlit.app").rstrip("/")
TICKERS = os.environ.get("WARM_TICKERS", "MU,SNDK,DELL,MRNA,MPC").split(",")
PAGES = ["/", "/mexico", "/watchlist"] + [f"/analysis?t={t.strip()}" for t in TICKERS if t.strip()]
PAGE_BUDGET = int(os.environ.get("PAGE_BUDGET", "150"))  # seconds per page


def wake_if_asleep(page) -> bool:
    btn = page.get_by_role("button", name="Yes, get this app back up!")
    try:
        btn.wait_for(timeout=8000)
    except PWTimeout:
        return False
    btn.click()
    print("  app was asleep: clicked wake button", flush=True)
    return True


def wait_until_done(page, budget: int) -> str:
    """Wait for the app iframe to finish running the script."""
    start = time.time()
    frame = None
    while time.time() - start < budget:
        frame = frame or next((f for f in page.frames if "/~/+/" in f.url), None)
        target = frame or page
        try:
            ready = target.locator("[data-testid='stAppViewContainer']").count() > 0
            running = target.locator("[data-testid='stStatusWidget']").count() > 0
            spinning = target.locator("[data-testid='stSpinner']").count() > 0
        except Exception:
            ready = running = spinning = False
        if ready and not running and not spinning and time.time() - start > 10:
            return f"done in {time.time() - start:.0f}s"
        time.sleep(3)
    return f"still running after {budget}s (left it warming)"


def main() -> int:
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        for i, path in enumerate(PAGES):
            url = BASE + path
            print(f"-> {url}", flush=True)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                if i == 0 and wake_if_asleep(page):
                    time.sleep(45)
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print("  " + wait_until_done(page, PAGE_BUDGET), flush=True)
            except Exception as e:  # keep going; one slow page should not stop the rest
                failures += 1
                print(f"  failed: {e}", flush=True)
        browser.close()
    return 1 if failures == len(PAGES) else 0


if __name__ == "__main__":
    sys.exit(main())
