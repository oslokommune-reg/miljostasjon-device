# main.py
# ------------------------------------------------------------
# Orchestrates discovery, continuous readers, aggregation and upload.
# - Readers continuously update an in-memory "latest_frames" map.
# - Aggregator (every 30s) snapshots latest frames (fresh enough and with
#   required keys) and stores one entry in the power-loss safe buffer
#   (SQLite, see module/storage.py).
# - Uploader (every SCHEDULE_SECONDS) sends the buffer in batches and deletes
#   each batch only after the API confirms it.
# - On SIGTERM (docker stop, controlled shutdown) a final upload is attempted
#   within a deadline before the process exits.
# - Webcam daily capture retained as before.
# ------------------------------------------------------------

import os
import signal
import threading
import time
from datetime import datetime

import schedule
from module.clock import is_clock_synchronized
from module.device import (
    FRESHNESS_SECONDS,  # fixed constant from device.py
    ReaderThread,
    Webcam,
    classify_roles,
    discover_devices,
)
from module.storage import ReadingBuffer
from module.uploader import Uploader
from module.utils.logger import setup_custom_logger
from tzlocal import get_localzone

# --------------------
# Fixed config (no getenv)
# --------------------
SCHEDULE_SECONDS = 300  # upload interval in seconds
CAPTURE_TIME = "07:25"  # daily webcam capture (HH:MM, local time)
STARTUP_DELAY = 20  # startup delay in seconds (allow NTP/udev settle)

DATA_DIR = "/container_storage"
BUFFER_DB_PATH = os.path.join(DATA_DIR, "buffer.db")

# Extra warmup so ReaderThread rekker å "merge" inn H17/H18/H22 før vi begynner å samle
AGGREGATOR_WARMUP_SECONDS = 60

# Do not store readings stamped with an unsynchronised clock (no RTC, see
# module/clock.py). If NTP has not synced after this long, store anyway.
CLOCK_SYNC_MAX_WAIT_SECONDS = 180

# Time allowed for the final upload after SIGTERM. Must be shorter than
# stop_grace_period in docker-compose.yml.
SHUTDOWN_UPLOAD_SECONDS = 25

# Test mode: synthetic frames, fast aggregation, uploads always disabled.
FAKE_DEVICES = os.getenv("FAKE_DEVICES") == "1"
AGGREGATE_SECONDS = 1 if FAKE_DEVICES else 30

REQUIRED_KEYS = {
    "loadlogger": ("PID", "V", "I", "P", "SOC", "CE", "H17"),  # H18 fjernet
    "charger": ("PID", "SER#", "V", "I", "VPV", "PPV", "H22"),
    "charger_2": ("PID", "SER#", "V", "I", "VPV", "PPV", "H22"),
}


# --------------------
# Loggers / Globals
# --------------------
main_logger = setup_custom_logger("main")

# In-memory latest frames from readers:
#   latest_frames[role] = { "PID": ..., ..., "_ts": iso-str }
latest_frames = {}

# Power-loss safe buffer + uploader
buffer = ReadingBuffer(BUFFER_DB_PATH)
uploader = Uploader(buffer, enabled=not FAKE_DEVICES)

# Webcam
webcam = Webcam()

# Internal state
_boot_time = time.time()
_role_ready_logged = set()  # so we don't spam logs every 30s
_clock_warning_logged = False
_stop = threading.Event()


# --------------------
# Helpers
# --------------------
def _role_has_required(role: str, frame: dict) -> bool:
    req = REQUIRED_KEYS.get(role)
    if not req:
        return True
    return all(k in frame for k in req)


def _age_seconds(now: datetime, ts_iso: str) -> float:
    try:
        from datetime import datetime as _dt

        return (now - _dt.fromisoformat(ts_iso)).total_seconds()
    except Exception:
        return float("inf")


def _clock_ready() -> bool:
    """True when timestamps can be trusted, or when we have waited long enough."""
    global _clock_warning_logged
    if is_clock_synchronized():
        return True
    if time.time() - _boot_time < CLOCK_SYNC_MAX_WAIT_SECONDS:
        main_logger.debug("Clock not synchronised yet; skipping this tick.")
        return False
    if not _clock_warning_logged:
        main_logger.warning(
            f"Clock still not synchronised after {CLOCK_SYNC_MAX_WAIT_SECONDS}s; "
            "storing readings anyway."
        )
        _clock_warning_logged = True
    return True


# --------------------
# Jobs
# --------------------
def aggregate_once():
    """
    Snapshot latest frames and write one entry into the buffer.
    Include only roles with frames fresher than FRESHNESS_SECONDS
    AND that contain the required keys for that role (H17/H18, H22, ...).
    """
    # Varm opp litt ekstra etter boot for å sikre at history-felter har rukket å komme
    if not FAKE_DEVICES and time.time() - _boot_time < (
        STARTUP_DELAY + AGGREGATOR_WARMUP_SECONDS
    ):
        main_logger.debug(
            "Aggregator warmup window not elapsed yet; skipping this tick."
        )
        return

    if not _clock_ready():
        return

    now = datetime.now(get_localzone())
    now_iso = now.isoformat()

    entry = {"timestamp": now_iso}
    included = []
    dropped = []

    # Copy keys to avoid concurrent modification during iteration
    for role in list(latest_frames.keys()):
        frame = latest_frames.get(role, {}) or {}
        ts = frame.get("_ts")
        if not ts:
            dropped.append((role, "missing_ts"))
            continue

        age = _age_seconds(now, ts)
        if age > FRESHNESS_SECONDS:
            dropped.append((role, f"stale:{int(age)}s"))
            continue

        # Check must-have keys
        if not _role_has_required(role, frame):
            # log at most once per role to avoid spam
            if role not in _role_ready_logged:
                missing = [k for k in REQUIRED_KEYS.get(role, ()) if k not in frame]
                main_logger.info(
                    f"Role '{role}' not ready; missing keys: {missing}. Will include once available."
                )
                _role_ready_logged.add(role)
            dropped.append((role, "missing_required"))
            continue

        # Copy without _ts for the output format
        clean = {k: v for k, v in frame.items() if k != "_ts"}
        entry[role] = clean
        included.append(role)

    # Per-tick lines are DEBUG: at INFO they would be ~3 journal entries a
    # minute, each costing several KB of SD writes. Problems are logged at
    # WARNING/ERROR, and the uploader logs a summary per upload.
    if not included:
        main_logger.debug(
            f"No fresh/ready frames for aggregation window; dropped={dropped}"
        )
        return

    try:
        seq = buffer.append(entry)
    except Exception as e:
        main_logger.error(f"Failed to store entry: {e}")
        return
    main_logger.debug(f"Stored entry {seq} with roles: {included}; dropped={dropped}")


def upload_in_background():
    # Run outside the scheduler thread so a slow network never delays
    # aggregation. Uploader itself prevents overlapping runs.
    threading.Thread(target=uploader.upload_pending, daemon=True).start()


def webcam_job():
    t = threading.Thread(target=webcam.trigger, daemon=True)
    t.start()
    main_logger.info(f"Daily webcam capture triggered at {CAPTURE_TIME}.")


def _handle_sigterm(signum, frame):
    main_logger.info("SIGTERM received; shutting down.")
    _stop.set()


def shutdown():
    """Final upload within a deadline, then leave the buffer in a clean state."""
    deadline = time.monotonic() + SHUTDOWN_UPLOAD_SECONDS
    uploader.upload_pending(deadline=deadline)
    main_logger.info(f"{buffer.count()} entries left in buffer at shutdown.")
    buffer.checkpoint()
    buffer.close()


# --------------------
# Bootstrap
# --------------------
if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        buffer.import_legacy_json(DATA_DIR)
        main_logger.info(f"{buffer.count()} entries pending in buffer at startup.")
        if FAKE_DEVICES:
            main_logger.warning("FAKE_DEVICES=1: synthetic data, uploads disabled.")

        main_logger.info(
            f"Delaying startup for {STARTUP_DELAY} seconds to allow time sync..."
        )
        if _stop.wait(STARTUP_DELAY):
            raise SystemExit

        # 1) Discover devices (ports + samples)
        readers = []
        if FAKE_DEVICES:
            from module.fake_devices import FakeReaderThread

            FakeReaderThread(latest_frames).start()
        else:
            devs = discover_devices()
            roles = classify_roles(devs)  # [(role, port), ...]

            # 2) Start dedicated readers
            for role, port in roles:
                r = ReaderThread(role=role, port=port, latest_frames=latest_frames)
                r.start()
                readers.append(r)
                main_logger.info(f"Started reader for {role} on {port}")

            if not readers:
                main_logger.warning(
                    "No devices discovered. Will continue and rely on future restarts/hotplug."
                )

        # 3) Schedule aggregator + uploader + webcam
        # Kick off an early upload so data left from the previous run is sent
        # quickly; the power windows can be as short as 10 minutes.
        schedule.every(AGGREGATE_SECONDS).seconds.do(aggregate_once)
        upload_in_background()
        schedule.every(SCHEDULE_SECONDS).seconds.do(upload_in_background)
        schedule.every().day.at(CAPTURE_TIME).do(webcam_job)

        # 4) Main loop
        while not _stop.is_set():
            schedule.run_pending()
            _stop.wait(1 if not FAKE_DEVICES else 0.2)

    except SystemExit:
        pass
    except Exception as e:
        main_logger.error(f"Fatal error in main: {e}")
    finally:
        shutdown()
