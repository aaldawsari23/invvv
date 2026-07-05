#!/usr/bin/env python3
"""Debug: dump Bing image search HTML to inspect structure."""
import requests, json, re
from bs4 import BeautifulSoup

q = "MGE30006 WHEELCHAIR BARIATRIC medical"
url = "https://www.bing.com/images/search"
params = {"q": q, "form": "HDRSC2", "first": "1"}
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
r = requests.get(url, params=params, headers=headers, timeout=15)
print("HTTP", r.status_code, "len", len(r.text))
soup = BeautifulSoup(r.text, "lxml")
items = soup.select("div.iuscp")
print(f"Found {len(items)} .iuscp items")
for i, item in enumerate(items[:3]):
    m = item.get("m", "")
    print(f"\n--- item {i} ---")
    if m:
        try:
            d = json.loads(m)
            print("  murl:", d.get("murl"))
            print("  turl:", d.get("turl"))
            print("  purl:", d.get("purl"))
            print("  all keys:", list(d.keys())[:10])
        except Exception as e:
            print("  json error:", e)
            print("  m starts:", m[:200])

# also try the .iusc variant
items2 = soup.select("a.iusc")
print(f"\nFound {len(items2)} a.iusc items")
for i, item in enumerate(items2[:3]):
    m = item.get("m", "")
    if m:
        try:
            d = json.loads(m)
            print(f"  item {i} murl:", d.get("murl"))
        except Exception:
            pass
