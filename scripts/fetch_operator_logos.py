#!/usr/bin/env python3
"""Download a small, curated set of operator logos for the static Pages artifact.

Source pages and reuse terms: https://commons.wikimedia.org/
These images represent operator trademarks, NOT endorsements of LuzMaker.
Downloads are best effort: missing logos simply do not render.
"""
from pathlib import Path
import urllib.parse
import urllib.request

# Filename, Commons media title (each source verified on Wikimedia Commons).
LOGOS = {
    "egged": "Egged logo.svg",
    "kavim": "KavimLogo.svg",
    "metropoline": "Metropoline buses logo.svg",
    "superbus": "Superbus logo.svg",
    "nateev-express": "Nateev Express Logo.svg",
    "beit-shemesh-express": "בית שמש אקספרס.svg",
}
USER_AGENT = "LuzMaker-Pages/1.0 (operator-logo cache; https://github.com/MOSHHHHHH/LuzMaker)"


def main():
    out = Path("_site/logos")
    out.mkdir(parents=True, exist_ok=True)
    for key, title in LOGOS.items():
        url = "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + urllib.parse.quote(title)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=22) as response:
                blob = response.read(600_001)
            if len(blob) > 600_000 or not blob.lstrip().startswith(b"<?xml") and not blob.lstrip().startswith(b"<svg"):
                raise ValueError("Unexpected content or oversized SVG")
            if b"<svg" not in blob[:2000]:
                raise ValueError("SVG element not found")
            (out / (key + ".svg")).write_bytes(blob)
            print("Fetched operator logo", key, len(blob), flush=True)
        except Exception as exc:
            print("Logo unavailable:", key, type(exc).__name__, str(exc), flush=True)


if __name__ == "__main__":
    main()
