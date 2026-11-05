"""No-network regression tests for the published-data freshness guard."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_freshness import age_hours, MAX_AGE_HOURS


class FreshnessTests(unittest.TestCase):
    def payload(self, age):
        timestamp = (datetime(2026, 11, 5, 12, tzinfo=timezone.utc) - timedelta(hours=age)).isoformat()
        return {"format": 2, "lines": [["480", "data.json"]], "updated": timestamp}

    def test_fresh(self):
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        self.assertLess(age_hours(self.payload(29), now), MAX_AGE_HOURS)

    def test_stale(self):
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        self.assertGreaterEqual(age_hours(self.payload(31), now), MAX_AGE_HOURS)

    def test_invalid_payload(self):
        with self.assertRaises(ValueError):
            age_hours({"format": 2, "lines": [], "updated": "2026-11-05T12:00:00+00:00"})

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            age_hours({"format": 2, "lines": [["480", "data.json"]], "updated": "2026-11-05T12:00:00"})

    def test_future_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            age_hours(self.payload(-2), datetime(2026, 11, 5, 12, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
