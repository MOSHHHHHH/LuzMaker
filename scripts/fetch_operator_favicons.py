#!/usr/bin/env python3
"""Cache operator-site favicons for LuzMaker.

Source priority: official GTFS agency_url website; Google s2/favicon as a
best-effort proxy for the SAME website when direct retrieval fails.
Only validated raster images are published. Failures do not block schedules.
"""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import struct
import urllib.error
import urllib.parse
import urllib.request

MAX_ICON = 256_000
MAX_HTML = 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; LuzMaker-favicon-cache/2.0)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "image/png,image/x-icon,image/vnd.microsoft.icon,image/webp,image/jpeg,text/html;q=0.7"}
GOOGLE_ICON_ENDPOINT = "https://www.google.com/s2/favicons"
ALLOWED_IMAGE_TYPES = ("png", "ico", "webp", "jpg")


def safe_url(url):
    """Reject local destinations, IP literals, credentials and non-TLS URLs."""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or parsed.port not in (None, 443) or len(url) > 2048):
            return False
        if not re.fullmatch(r"[a-z0-9.-]+", host, re.I) or "." not in host or ".." in host:
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        return all(ipaddress.ip_address(entry[4][0]).is_global for entry in
                   socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
    except (ValueError, socket.gaierror, OSError):
        return False


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise ValueError("Unsafe redirect target")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirect())


def get(url, limit, partial=False):
    if not safe_url(url):
        raise ValueError("Unsafe operator site URL")
    req = urllib.request.Request(url, headers=HEADERS)
    with OPENER.open(req, timeout=9) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            if not partial:
                raise ValueError("Oversized response")
            data = data[:limit]  # The icon links normally appear inside <head>.
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
        if href and ("icon" in rel or "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel):
            self.links.append((str(href), str(values.get("sizes", "")), str(values.get("type", ""))))


def image_extension(data):
    """Content-based format check. Unsafe SVG and arbitrary HTML are not served."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return "png"
    if data.startswith(b"\x00\x00\x01\x00") and len(data) >= 6:
        return "ico"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


def png_dimensions(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
        return None
    return struct.unpack(">II", data[16:24])


def official_site_url(raw):
    raw = str(raw or "").strip()
    if raw.lower().startswith("http://"):
        raw = "https://" + raw[7:]
    return raw


def direct_favicon(site):
    """Try declared icons, including touch icons; then common root filenames."""
    candidates = []
    reason = ""
    try:
        html, actual = get(site, MAX_HTML, partial=True)
        parser = FaviconLinks()
        parser.feed(html.decode("utf-8", errors="replace"))
        for href, sizes, mime in parser.links:
            candidate = urllib.parse.urljoin(actual, href)
            if not safe_url(candidate):
                continue
            sizes_found = re.findall(r"\d{1,4}x\d{1,4}", sizes.lower())
            score = max((min(int(s.split("x")[0]), 512) for s in sizes_found), default=0)
            if "png" in mime or ".png" in href.lower():
                score += 20
            if "svg" in mime or ".svg" in href.lower():
                score -= 100  # Do not serve untrusted SVG to users.
            candidates.append((score, candidate))
        candidates.sort(key=lambda x: x[0], reverse=True)
        base = actual
    except Exception as exc:
        reason = "site: " + type(exc).__name__
        base = site
    base_parts = urllib.parse.urlsplit(base)
    origin = urllib.parse.urlunsplit(("https", base_parts.netloc, "/", "", ""))
    candidates = [url for _, url in candidates[:8]] + [
        urllib.parse.urljoin(origin, path) for path in
        ("favicon.ico", "favicon.png", "favicon-32x32.png", "favicon-192x192.png",
         "apple-touch-icon.png", "apple-touch-icon-precomposed.png")
    ]
    tried = set()
    for candidate in candidates:
        if candidate in tried:
            continue
        tried.add(candidate)
        try:
            raw, _ = get(candidate, MAX_ICON)
            ext = image_extension(raw)
            if ext:
                return raw, ext, "direct"
        except Exception as exc:
            reason = type(exc).__name__
    return None, None, reason or "no supported icon"


def google_favicon(site):
    """Google's undocumented s2 proxy is optional and never used in the UI."""
    hostname = urllib.parse.urlsplit(site).hostname
    if not hostname:
        return None, None, "missing hostname"
    query = urllib.parse.urlencode({"domain": hostname, "sz": "128"})
    url = GOOGLE_ICON_ENDPOINT + "?" + query
    try:
        data, final_url = get(url, MAX_ICON)
        host = urllib.parse.urlsplit(final_url).hostname or ""
        # The image must come from Google's own service/CDN.
        if host != "www.google.com" and not re.fullmatch(r"t[0-9]\.gstatic\.com", host):
            return None, None, "unexpected Google redirect"
        if image_extension(data) != "png":
            return None, None, "Google returned non-PNG"
        dimensions = png_dimensions(data)
        if not dimensions or min(dimensions) < 32:
            return None, None, "Google fallback/low-resolution icon"
        return data, "png", "google"
    except urllib.error.HTTPError as exc:
        return None, None, f"Google HTTP {exc.code}"
    except Exception as exc:
        return None, None, "Google: " + type(exc).__name__


def favicon_for(operator):
    key, agency = operator
    name = str(agency.get("name") or key).strip()
    original = agency.get("url", "")
    extra_sites = agency.get("fallback_urls", [])
    candidates = [original, *extra_sites]
    attempted, problems = set(), []
    for index, raw_site in enumerate(candidates):
        site = official_site_url(raw_site)
        if not site or site in attempted:
            continue
        attempted.add(site)
        if not safe_url(site):
            problems.append("GTFS URL invalid" if index == 0 else "fallback URL invalid")
            continue
        # Within each site, always try direct discovery before Google.
        data, ext, result = direct_favicon(site)
        if data:
            return key, name, data, ext, result, site, "gtfs" if index == 0 else "fallback"
        proxy_data, proxy_ext, proxy_result = google_favicon(site)
        if proxy_data:
            return key, name, proxy_data, proxy_ext, proxy_result, site, "gtfs" if index == 0 else "fallback"
        problems.append(("GTFS " if index == 0 else "fallback ") + result + "; " + proxy_result)
    return key, name, None, None, " | ".join(problems) or "missing website", "", "missing"


def build_icons(root):
    data = root / "data"
    agencies = json.loads((data / "agencies.json").read_text(encoding="utf-8"))
    fallback_path = Path(__file__).resolve().parents[1] / "data" / "operator-website-fallbacks.json"
    fallbacks = json.loads(fallback_path.read_text(encoding="utf-8")) if fallback_path.exists() else {}
    for key, agency in agencies.items():
        agency["fallback_urls"] = fallbacks.get(key, [])
    icons = root / "operator-icons"
    icons.mkdir(parents=True, exist_ok=True)
    mapping, report = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(favicon_for, item) for item in agencies.items()]
        for future in concurrent.futures.as_completed(futures):
            key, name, payload, ext, source, selected_site, site_kind = future.result()
            record = {"agency_id": key, "name": name, "website": agencies[key].get("url", ""),
                      "fallback_websites": agencies[key].get("fallback_urls", []),
                      "selected_website": selected_site, "website_source": site_kind,
                      "source": source, "status": "found" if payload else "missing"}
            if payload:
                filename = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20] + "." + ext
                (icons / filename).write_bytes(payload)
                mapping[key] = "./operator-icons/" + filename
            report.append(record)
    report.sort(key=lambda row: row["agency_id"])
    (data / "operator-icons.json").write_text(
        json.dumps(mapping, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (data / "operator-icons-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {"direct": 0, "google": 0, "missing": 0}
    for row in report:
        counts[row["source"] if row["status"] == "found" else "missing"] += 1
        print("Favicon:", row["agency_id"], row["name"], row["status"], row["source"],
              row["website_source"], row["selected_website"], flush=True)
    print(f"Favicons downloaded: {len(mapping)}/{len(agencies)} operators "
          f"(direct={counts['direct']}, google={counts['google']}, missing={counts['missing']})",
          flush=True)


if __name__ == "__main__":
    build_icons(Path("_site"))
