# fake_devices.py
# ------------------------------------------------------------
# Test mode only (FAKE_DEVICES=1): publishes synthetic frames for all roles
# so the buffer can be exercised on a Pi without Victron equipment, e.g.
# during power-cut testing. main.py disables uploads in this mode, so fake
# data never reaches the API.
# ------------------------------------------------------------

import threading
import time
from datetime import datetime

from tzlocal import get_localzone

FAKE_FRAMES = {
    "loadlogger": {"PID": "0xA389", "V": "12800", "I": "-500", "P": "-6",
                   "SOC": "950", "CE": "-1000", "H17": "100"},
    "charger": {"PID": "0xA057", "SER#": "HQ0000001", "V": "12800", "I": "1000",
                "VPV": "18000", "PPV": "15", "H22": "50"},
}


class FakeReaderThread(threading.Thread):
    def __init__(self, latest_frames: dict, interval: float = 1.0):
        super().__init__(daemon=True)
        self.latest_frames = latest_frames
        self.interval = interval

    def run(self):
        while True:
            ts = datetime.now(get_localzone()).isoformat()
            for role, frame in FAKE_FRAMES.items():
                self.latest_frames[role] = {**frame, "_ts": ts}
            time.sleep(self.interval)
