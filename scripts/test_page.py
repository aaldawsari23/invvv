#!/usr/bin/env python3
"""
Start a local HTTP server and use Playwright to load index.html with
one of the user's input files, then inspect what the analyzer sees.
This will tell us EXACTLY what r.sku, r.name etc. contain.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/z/my-project/download")
TEST_FILE = Path("/home/z/my-project/upload/Pasted Content_1783208594796.txt")


def main():
    # Check playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright

    # Start a simple HTTP server so fetch() can load product_index.json
    cwd = os.getcwd()
    os.chdir(ROOT)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8765"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    os.chdir(cwd)
    time.sleep(1.5)
    print("HTTP server started on http://localhost:8765")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()

            # Capture console logs
            console_msgs = []
            page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))

            page.goto("http://localhost:8765/index.html", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Read the test file content
            with open(TEST_FILE, "rb") as f:
                file_bytes = f.read()

            # Upload the file by setting it on the file input
            file_input = page.locator('#fileInput')
            file_input.set_input_files({
                "name": "test_inventory.txt",
                "mimeType": "text/plain",
                "buffer": file_bytes,
            })

            # Wait for analysis to complete
            page.wait_for_timeout(8000)

            # Inspect state in JS
            state_info = page.evaluate("""() => {
                // Access the IIFE's state via the rendered DOM
                const cards = document.querySelectorAll('.card');
                const results = [];
                cards.forEach((c, i) => {
                    if (i >= 10) return; // first 10 only
                    const titleEl = c.querySelector('.card-title');
                    const metaDivs = c.querySelectorAll('.meta-mini div');
                    const pills = c.querySelectorAll('.pill');
                    const imgWrap = c.querySelector('.card-img-wrap');
                    results.push({
                        title: titleEl ? titleEl.textContent : '',
                        meta: Array.from(metaDivs).map(d => d.textContent),
                        pills: Array.from(pills).map(p => p.textContent),
                        hasImage: !!imgWrap,
                        imgSrc: imgWrap ? imgWrap.querySelector('img')?.getAttribute('src') : null,
                        innerHTML_short: c.innerHTML.substring(0, 500)
                    });
                });
                return {
                    cardsCount: cards.length,
                    first10: results,
                    productIndexLoaded: window.__PRODUCT_INDEX__ !== null,
                    productIndexKeys: window.__PRODUCT_INDEX__ ? {
                        byCode: Object.keys(window.__PRODUCT_INDEX__.byCode).length,
                        byBarcode: Object.keys(window.__PRODUCT_INDEX__.byBarcode).length,
                        byDesc: window.__PRODUCT_INDEX__.byDesc.length
                    } : null
                };
            }""")

            print("\n=== Page State ===")
            print(f"Cards rendered: {state_info['cardsCount']}")
            print(f"Product index loaded: {state_info['productIndexLoaded']}")
            print(f"Index keys: {state_info['productIndexKeys']}")

            print("\n=== First 10 Cards ===")
            for i, c in enumerate(state_info['first10']):
                print(f"\nCard {i}:")
                print(f"  Title: {c['title'][:80]}")
                print(f"  Pills: {c['pills']}")
                print(f"  Meta: {c['meta']}")
                print(f"  Has image: {c['hasImage']}")
                if c['imgSrc']:
                    print(f"  Image src: {c['imgSrc']}")

            print("\n=== Console messages ===")
            for m in console_msgs[-20:]:
                print(m)

            # Also dump the raw item data via JS debugger
            print("\n=== Raw item data (first 3 items) ===")
            raw_items = page.evaluate("""() => {
                // Try to grab items by re-running parseFile on the same input
                // We can't access the IIFE state directly, but we can inspect
                // what's in the DOM
                const cards = document.querySelectorAll('.card');
                const out = [];
                cards.forEach((c, i) => {
                    if (i >= 3) return;
                    const metaDivs = c.querySelectorAll('.meta-mini div');
                    const titleEl = c.querySelector('.card-title');
                    out.push({
                        title: titleEl?.textContent || '',
                        meta: Array.from(metaDivs).map(d => d.textContent)
                    });
                });
                return out;
            }""")
            for r in raw_items:
                print(json.dumps(r, ensure_ascii=False, indent=2))

            browser.close()
    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    main()
