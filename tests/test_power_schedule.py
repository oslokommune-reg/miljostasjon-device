# Run: python3 -m unittest discover -s tests -v
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "power"))

from power_schedule import ScheduleError, current_window_end, decide, parse_schedule  # noqa: E402
from schedule_source import FileSource, load_schedule  # noqa: E402

OSLO = ZoneInfo("Europe/Oslo")
CONFIG = {
    "timezone": "Europe/Oslo",
    "windows": [{"start": "07:00", "end": "07:30"}, {"start": "13:00", "end": "13:10"}],
    "shutdown_lead_minutes": 3,
    "start_tolerance_minutes": 10,
    "unsynced_max_uptime_minutes": 7,
    "outside_window_grace_minutes": 10,
}
SCHED = parse_schedule(CONFIG)
UP = timedelta(minutes=1)


def oslo(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=OSLO).astimezone(timezone.utc)


class DecideTests(unittest.TestCase):
    def test_in_window_before_lead(self):
        d = decide(SCHED, oslo(2026, 6, 1, 7, 20), UP, True)
        self.assertFalse(d.shutdown)
        self.assertIn("07:27", d.reason)

    def test_in_window_at_lead(self):
        self.assertTrue(decide(SCHED, oslo(2026, 6, 1, 7, 27), UP, True).shutdown)
        self.assertTrue(decide(SCHED, oslo(2026, 6, 1, 13, 7), UP, True).shutdown)
        self.assertFalse(decide(SCHED, oslo(2026, 6, 1, 13, 6), UP, True).shutdown)

    def test_relay_slightly_early_counts_as_window(self):
        # Booted 06:52 because the relay clock is ahead: in window, not "outside".
        d = decide(SCHED, oslo(2026, 6, 1, 6, 52), timedelta(minutes=15), True)
        self.assertFalse(d.shutdown)
        self.assertIn("in power window", d.reason)

    def test_outside_window_grace(self):
        now = oslo(2026, 6, 1, 10, 0)
        self.assertFalse(decide(SCHED, now, timedelta(minutes=9), True).shutdown)
        self.assertTrue(decide(SCHED, now, timedelta(minutes=10), True).shutdown)

    def test_unsynced_clock_uses_uptime(self):
        # A wrong clock that happens to look "in window" must not matter.
        now = oslo(2026, 6, 1, 7, 10)
        self.assertFalse(decide(SCHED, now, timedelta(minutes=6), False).shutdown)
        self.assertTrue(decide(SCHED, now, timedelta(minutes=7), False).shutdown)

    def test_unsynced_limit_fits_shortest_window(self):
        shortest = min(
            (datetime.combine(datetime.today(), w.end) - datetime.combine(datetime.today(), w.start))
            for w in SCHED.windows
        )
        self.assertLess(SCHED.unsynced_max_uptime, shortest)


class DaylightSavingTests(unittest.TestCase):
    def test_summer_and_winter_same_wall_clock(self):
        # 07:27 local is 05:27 UTC in summer and 06:27 UTC in winter.
        summer = datetime(2026, 7, 1, 5, 27, tzinfo=timezone.utc)
        winter = datetime(2026, 1, 15, 6, 27, tzinfo=timezone.utc)
        self.assertTrue(decide(SCHED, summer, UP, True).shutdown)
        self.assertTrue(decide(SCHED, winter, UP, True).shutdown)
        self.assertFalse(decide(SCHED, summer - timedelta(minutes=1), UP, True).shutdown)
        self.assertFalse(decide(SCHED, winter - timedelta(minutes=1), UP, True).shutdown)

    def test_dst_change_days(self):
        for day in [(2026, 3, 29), (2026, 10, 25)]:  # spring forward, fall back
            self.assertEqual(current_window_end(SCHED, oslo(*day, 7, 10)), oslo(*day, 7, 30))
            self.assertTrue(decide(SCHED, oslo(*day, 13, 7), UP, True).shutdown)

    def test_window_in_nonexistent_and_repeated_hour(self):
        cfg = dict(CONFIG, windows=[{"start": "02:00", "end": "03:30"}])
        s = parse_schedule(cfg)
        # Spring forward: 02:00-03:00 does not exist. The window runs from
        # 02:00 CET (01:00 UTC) to 03:30 CEST (01:30 UTC).
        self.assertIsNotNone(current_window_end(s, datetime(2026, 3, 29, 1, 15, tzinfo=timezone.utc)))
        self.assertIsNone(current_window_end(s, datetime(2026, 3, 29, 0, 45, tzinfo=timezone.utc)))
        # Fall back: 02:00-03:00 happens twice; both are inside the window.
        self.assertIsNotNone(current_window_end(s, datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)))
        self.assertIsNotNone(current_window_end(s, datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)))

    def test_window_across_midnight(self):
        s = parse_schedule(dict(CONFIG, windows=[{"start": "23:50", "end": "00:20"}]))
        self.assertEqual(current_window_end(s, oslo(2026, 6, 1, 23, 55)), oslo(2026, 6, 2, 0, 20))
        self.assertEqual(current_window_end(s, oslo(2026, 6, 2, 0, 5)), oslo(2026, 6, 2, 0, 20))
        self.assertIsNone(current_window_end(s, oslo(2026, 6, 2, 0, 30)))


class ValidationTests(unittest.TestCase):
    def test_rejects_bad_config(self):
        bad = [
            dict(CONFIG, timezone="Mars/Olympus"),
            dict(CONFIG, windows=[]),
            dict(CONFIG, windows=[{"start": "7:00", "end": "07:30"}]),
            dict(CONFIG, windows=[{"start": "07:00", "end": "07:00"}]),
            dict(CONFIG, shutdown_lead_minutes=0),
            dict(CONFIG, unsynced_max_uptime_minutes="7"),
        ]
        for cfg in bad:
            with self.assertRaises(ScheduleError, msg=cfg):
                parse_schedule(cfg)

    def test_repo_config_is_valid(self):
        with open(os.path.join(REPO, "config", "power_schedule.json")) as f:
            parse_schedule(json.load(f))


class FailingSource:
    def fetch(self):
        raise OSError("network down")


class StaticSource:
    def __init__(self, data):
        self.data = data

    def fetch(self):
        return self.data


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cache = os.path.join(self.dir, "cache.json")

    def test_remote_ok_is_cached(self):
        _, _, from_remote = load_schedule(StaticSource(CONFIG), self.cache)
        self.assertTrue(from_remote)
        self.assertTrue(os.path.exists(self.cache))

    def test_falls_back_to_last_known_good(self):
        load_schedule(StaticSource(CONFIG), self.cache)
        s, origin, from_remote = load_schedule(FailingSource(), self.cache)
        self.assertFalse(from_remote)
        self.assertEqual(origin, self.cache)

    def test_invalid_remote_does_not_replace_cache(self):
        load_schedule(StaticSource(CONFIG), self.cache)
        load_schedule(StaticSource({"timezone": "x"}), self.cache)
        with open(self.cache) as f:
            self.assertEqual(json.load(f), CONFIG)

    def test_bundled_fallback_without_cache(self):
        bundled = os.path.join(REPO, "config", "power_schedule.json")
        _, origin, _ = load_schedule(FailingSource(), self.cache, [FileSource(bundled)])
        self.assertEqual(origin, bundled)

    def test_no_source_raises(self):
        with self.assertRaises(ScheduleError):
            load_schedule(FailingSource(), self.cache)


if __name__ == "__main__":
    unittest.main()
