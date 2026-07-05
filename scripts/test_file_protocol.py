#!/usr/bin/env python3
"""Test that index.html works when opened directly from file:// (no HTTP server)."""
import os
import sys
import time
from pathlib import Path

ROOT = Path("/home/z/my-project/download")
TEST_FILE = Path("/home/z/my-project/upload/Pasted Content_1783208594796.txt")


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        console_msgs = []
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console_msgs.append(f"[ERROR] {e}"))

        # Open directly from file://  — NO HTTP SERVER
        file_url = f"file://{ROOT}/index.html"
        print(f"Opening: {file_url}")
        page.goto(file_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Upload a file
        with open(TEST_FILE, "rb") as f:
            file_bytes = f.read()

        page.locator('#fileInput').set_input_files({
            "name": "test.txt",
            "mimeType": "text/plain",
            "buffer": file_bytes,
        })

        page.wait_for_timeout(8000)

        # Inspect results
        info = page.evaluate("""() => {
            const cards = document.querySelectorAll('.card');
            const withImg = document.querySelectorAll('.card .card-img-wrap').length;
            const withFailedImg = document.querySelectorAll('.card .card-img-wrap.img-failed').length;
            return {
                cardsCount: cards.length,
                withImage: withImg,
                withFailedImage: withFailedImg,
                productIndexLoaded: window.__PRODUCT_INDEX__ !== null,
                usedEmbedded: !!window.__EMBEDDED_PRODUCT_INDEX__,
                indexKeys: window.__PRODUCT_INDEX__ ? {
                    byCode: Object.keys(window.__PRODUCT_INDEX__.byCode).length,
                    byBarcode: Object.keys(window.__PRODUCT_INDEX__.byBarcode).length,
                    byDesc: window.__PRODUCT_INDEX__.byDesc.length
                } : null
            };
        }""")

        print("\n=== Results from file:// (NO SERVER) ===")
        print(f"  Cards rendered:      {info['cardsCount']}")
        print(f"  Cards with image:    {info['withImage']}")
        print(f"  Failed image loads:  {info['withFailedImage']}")
        print(f"  Product index loaded: {info['productIndexLoaded']}")
        print(f"  Used embedded data:   {info['usedEmbedded']}")
        print(f"  Index keys:           {info['indexKeys']}")

        # First 5 cards details
        cards = page.evaluate("""() => {
            const cards = document.querySelectorAll('.card');
            const out = [];
            cards.forEach((c, i) => {
                if (i >= 5) return;
                const title = c.querySelector('.card-title')?.textContent || '';
                const img = c.querySelector('.card-img');
                out.push({
                    title: title.substring(0, 60),
                    hasImage: !!img,
                    imgSrc: img ? img.getAttribute('src') : null,
                    imgLoaded: img ? (img.complete && img.naturalWidth > 0) : false
                });
            });
            return out;
        }""")
        print("\n=== First 5 cards ===")
        for i, c in enumerate(cards):
            status = "✓ image" if c['hasImage'] and c['imgLoaded'] else "✗ no img"
            print(f"  Card {i}: [{status}] {c['title']}")
            if c['imgSrc']:
                print(f"          src: {c['imgSrc']}  loaded: {c['imgLoaded']}")

        print("\n=== Console messages ===")
        for m in console_msgs[-15:]:
            print(f"  {m}")

        browser.close()


if __name__ == "__main__":
    main()
