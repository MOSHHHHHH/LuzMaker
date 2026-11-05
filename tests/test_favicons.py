"""Offline validation for favicon-only operator branding."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_operator_favicons import FaviconLinks, build_icons, image_extension, safe_url, favicon_for, png_dimensions


class FaviconTests(unittest.TestCase):
    def test_untrusted_urls_rejected(self):
        for url in ["http://example.com/icon.ico", "https://127.0.0.1/icon.ico",
                    "https://localhost/icon.ico", "file:///etc/passwd",
                    "https://admin:pass@example.com/favicon.ico", "https://example.com:8080/a"]:
            self.assertFalse(safe_url(url), url)

    def test_image_signature_required(self):
        self.assertEqual(image_extension(b"\x89PNG\r\n\x1a\n" + b"\x00"*16), "png")
        self.assertEqual(image_extension(b"\x00\x00\x01\x00anything"), "ico")
        self.assertIsNone(image_extension(b"<svg onload='alert(1)'></svg>"))
        self.assertIsNone(image_extension(b"<html>not an image</html>"))

    def test_html_icon_links(self):
        parser = FaviconLinks()
        parser.feed('<link rel="icon" type="image/png" sizes="64x64" href="/assets/icon.png">'
                    '<link rel="stylesheet" href="/styles.css">')
        self.assertEqual(parser.links, [("/assets/icon.png", "64x64", "image/png")])

    def test_touch_icon_detected(self):
        parser = FaviconLinks()
        parser.feed('<link rel="apple-touch-icon" sizes="180x180" href="/touch.png">')
        self.assertEqual(parser.links[0][0], "/touch.png")

    def test_google_only_when_direct_missing(self):
        with patch("fetch_operator_favicons.safe_url", return_value=True), \
             patch("fetch_operator_favicons.direct_favicon", return_value=(None, None, "none")), \
             patch("fetch_operator_favicons.google_favicon", return_value=(b"png", "png", "google")):
            key, name, data, ext, source, site, kind = favicon_for(("42", {"name": "Operator", "url": "https://company.example"}))
            self.assertEqual((key, name, source), ("42", "Operator", "google"))
        with patch("fetch_operator_favicons.safe_url", return_value=True), \
             patch("fetch_operator_favicons.direct_favicon", return_value=(b"local", "ico", "direct")), \
             patch("fetch_operator_favicons.google_favicon") as google:
            self.assertEqual(favicon_for(("42", {"name": "Operator", "url": "https://company.example"}))[4], "direct")
            google.assert_not_called()

    def test_website_fallback_after_gtfs_failure(self):
        attempts = []
        def direct(site):
            attempts.append(("direct", site))
            return (b"image", "ico", "direct") if "verified.example" in site else (None, None, "HTTPError")
        def google(site):
            attempts.append(("google", site))
            return None, None, "Google HTTP 404"
        operator = ("37", {"name": "Operator", "url": "https://old.example/",
                           "fallback_urls": ["https://verified.example/"]})
        with patch("fetch_operator_favicons.safe_url", return_value=True), \
             patch("fetch_operator_favicons.direct_favicon", side_effect=direct), \
             patch("fetch_operator_favicons.google_favicon", side_effect=google):
            key, name, data, ext, source, site, kind = favicon_for(operator)
        self.assertEqual((source, kind, site), ("direct", "fallback", "https://verified.example/"))
        self.assertEqual(attempts, [
            ("direct", "https://old.example/"), ("google", "https://old.example/"),
            ("direct", "https://verified.example/")])

    def test_only_successful_agencies_in_local_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "agencies.json").write_text(
                json.dumps({"a": {"url": "https://example.org", "name": "Test"},
                            "b": {"url": "", "name": "No image"}}))
            def fake_icon(item):
                if item[0] == "a":
                    return "a", "Test", b"\x89PNG\r\n\x1a\n" + b"\x00"*16, "png", "direct", "https://example.org", "gtfs"
                return "b", "No image", None, None, "missing website", "", "missing"
            with patch("fetch_operator_favicons.favicon_for", side_effect=fake_icon):
                build_icons(root)
            mapping = json.loads((root / "data" / "operator-icons.json").read_text())
            self.assertEqual(list(mapping), ["a"])
            self.assertTrue((root / mapping["a"].removeprefix("./")).exists())
            report = json.loads((root / "data" / "operator-icons-report.json").read_text())
            self.assertEqual([entry["status"] for entry in report], ["found", "missing"])
            self.assertEqual(report[0]["selected_website"], "https://example.org")


if __name__ == "__main__":
    unittest.main()
