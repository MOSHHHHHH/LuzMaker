#!/usr/bin/env python3
"""Cache favicons from GTFS agency_url only. No external logo databases.

Best effort: missing/invalid icons are omitted. No JavaScript, SVG, HTML or
remote image URL is ever embedded into the public site. All icons are local.
"""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX_ICON = 256_000
MAX_HTML = 256_000
USER_AGENT = "Mozilla/5.0 (compatible; LuzMaker-favicon-cache/1.0)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "image/png,image/x-icon,image/vnd.microsoft.icon,image/webp,image/jpeg,text/html;q=0.7"}
FORMATS = {
    "png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "ico": lambda b: b[:4] == b"\x00\x00\x01\x00",
    "webp": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP",
    "jpg": lambda b: b.startswith(b"\xff\xd8\xff"),
}


def safe_url(url):
    """Deny IP literals, non-HTTPS endpoints, ports and private DNS results."""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or parsed.port not in (None, 443) or len(url) > 2048):
            return False
        if not re.fullmatch(r"[a-z0-9.-]+", host, re.I) or "." not in host:
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
            address = ipaddress.ip_address(entry[4][0])
            if not address.is_global:
                return False
        return True
    except (ValueError, socket.gaierror, OSError):
        return False


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise ValueError("Unsafe redirect target")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirect())


def get(url, limit):
    if not safe_url(url):
        raise ValueError("Unsafe operator site URL")
    req = urllib.request.Request(url, headers=HEADERS)
    with OPENER.open(req, timeout=8) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Oversized response")
        return data, response.geturl()


class FaviconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        values = dict(attrs)
        rel = str(values.get("rel", "")).lower().split()
        href = values.get("href")
        if href and ("icon" in rel or "shortcut" in rel and "icon" in rel):
            self.links.append((str(href), str(values.get("sizes", "")), str(values.get("type", ""))))


def image_extension(data):
    return next((ext for ext, valid in FORMATS.items() if valid(data)), None)


def favicon_for(operator):
    key, agency = operator
    url = agency.get("url", "")
    if not safe_url(url):
        return key, None, None
    try:
        html, actual = get(url, MAX_HTML)
        parser = FaviconLinks()
        parser.feed(html.decode("utf-8", errors="replace"))
        candidates = []
        for href, sizes, mime in parser.links:
            candidate = urllib.parse.urljoin(actual, href)
            if not safe_url(candidate):
                continue
            # Prefer explicit larger PNG / ICO entries, not apple-touch-only icons.
            score = 0
            sizes_found = re.findall(r"\d{1,4}x\d{1,4}", sizes.lower())
            if sizes_found:
                score = max(min(int(size.split("x")[0]), 512) for size in sizes_found)
            if "png" in mime or ".png" in href.lower():
                score += 20
            candidates.append((score, candidate))
        candidates.sort(reverse=True)
        for candidate in [u for _, u in candidates[:6]] + [urllib.parse.urljoin(actual, "/favicon.ico")]:
            try:
                raw, _ = get(candidate, MAX_ICON)
                ext = image_extension(raw)
                if ext:
                    return key, raw, ext
            except (ValueError, OSError, urllib.error.URLError):
                continue
    except (ValueError, OSError, urllib.error.URLError):
        # Sites that disallow homepage access may still expose /favicon.ico.
        try:
            parsed = urllib.parse.urlsplit(url)
            ico_url = urllib.parse.urlunsplit(("https", parsed.netloc, "/favicon.ico", "", ""))
            raw, _ = get(ico_url, MAX_ICON)
            ext = image_extension(raw)
            if ext:
                return key, raw, ext
        except (ValueError, OSError, urllib.error.URLError):
            pass
    return key, None, None


def build_icons(root):
    data = root / "data"
    agencies = json.loads((data / "agencies.json").read_text(encoding="utf-8"))
    icons = root / "operator-icons"
    icons.mkdir(parents=True, exist_ok=True)
    mapping = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(favicon_for, item) for item in agencies.items()]
        for future in concurrent.futures.as_completed(futures):
            key, payload, ext = future.result()
            if not payload:
                continue
            filename = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20] + "." + ext
            (icons / filename).write_bytes(payload)
            mapping[key] = "./operator-icons/" + filename
    (data / "operator-icons.json").write_text(
        json.dumps(mapping, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Favicons downloaded: {len(mapping)}/{len(agencies)} operators", flush=True)


if __name__ == "__main__":
    build_icons(Path("_site"))
