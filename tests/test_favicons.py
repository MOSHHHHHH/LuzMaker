"""Offline validation for favicon-only operator branding."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_operator_favicons import FaviconLinks, build_icons, image_extension, safe_url


class FaviconTests(unittest.TestCase):
    def test_untrusted_urls_rejected(self):
        for url in ["http://example.com/icon.ico", "https://127.0.0.1/icon.ico",
                    "https://localhost/icon.ico", "file:///etc/passwd",
                    "https://admin:pass@example.com/favicon.ico", "https://example.com:8080/a"]:
            self.assertFalse(safe_url(url), url)

    def test_image_signature_required(self):
        self.assertEqual(image_extension(b"\x89PNG\r\n\x1a\nanything"), "png")
        self.assertEqual(image_extension(b"\x00\x00\x01\x00anything"), "ico")
        self.assertIsNone(image_extension(b"<svg onload='alert(1)'></svg>"))
        self.assertIsNone(image_extension(b"<html>not an image</html>"))

    def test_html_icon_links(self):
        parser = FaviconLinks()
        parser.feed('<link rel="icon" type="image/png" sizes="64x64" href="/assets/icon.png">'
                    '<link rel="stylesheet" href="/styles.css">')
        self.assertEqual(parser.links, [("/assets/icon.png", "64x64", "image/png")])

    def test_only_successful_agencies_in_local_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            (root / "data" / "agencies.json").write_text(
                json.dumps({"a": {"url": "https://example.org", "name": "Test"},
                            "b": {"url": "", "name": "No image"}}))
            def fake_icon(item):
                if item[0] == "a":
                    return "a", b"\x89PNG\r\n\x1a\n" + b"abc", "png"
                return "b", None, None
            with patch("fetch_operator_favicons.favicon_for", side_effect=fake_icon):
                build_icons(root)
            mapping = json.loads((root / "data" / "operator-icons.json").read_text())
            self.assertEqual(list(mapping), ["a"])
            self.assertTrue((root / mapping["a"].removeprefix("./")).exists())


if __name__ == "__main__":
    unittest.main()
