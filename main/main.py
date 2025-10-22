# main.py
# ------------------------------------------------------------
# Orchestrates discovery, continuous readers, aggregation and upload.
# - Readers continuously update an in-memory "latest_frames" map.
# - Aggregator (every 60s) snapshots latest frames (fresh enough and with
#   required keys) and appends an entry to /container_storage/temporary_device_data.json.
# - Uploader (every SCHEDULE_SECONDS) sends the buffer and clears it on 200.
# - Webcam daily capture retained as before.
# ------------------------------------------------------------

import threading
import time
from datetime import datetime

import schedule
from module.device import (
    FRESHNESS_SECONDS,  # fixed constant from device.py
    FileBuffer,
    ReaderThread,
    Webcam,
    classify_roles,
    discover_devices,
)
from module.utils.logger import setup_custom_logger
from tzlocal import get_localzone

# --------------------
# Fixed config (no getenv)
# --------------------
SCHEDULE_SECONDS = 300  # upload interval in seconds
CAPTURE_TIME = "07:25"  # daily webcam capture (HH:MM, local time)
STARTUP_DELAY = 20  # startup delay in seconds (allow NTP/udev settle)

BUFFER_PATH = "/container_storage/temporary_device_data.json"

# Extra warmup so ReaderThread rekker å "merge" inn H17/H18/H22 før vi begynner å samle
AGGREGATOR_WARMUP_SECONDS = 60

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

# File buffer
buffer = FileBuffer(BUFFER_PATH)

# Webcam
webcam = Webcam()

# Internal state
_boot_time = time.time()
_role_ready_logged = set()  # so we don't spam logs every 30s


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
    if time.time() - _boot_time < (STARTUP_DELAY + AGGREGATOR_WARMUP_SECONDS):
        main_logger.info(
            "Aggregator warmup window not elapsed yet; skipping this tick."
        )
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

    if not included:
        main_logger.info(
            f"No fresh/ready frames for aggregation window; dropped={dropped}"
        )
        return

    buffer.append(entry)
    main_logger.info(f"Aggregated entry with roles: {included}; dropped={dropped}")


def upload_once():
    ok = buffer.upload_and_clear()
    if ok:
        main_logger.info("Upload job: success or nothing to upload.")
    else:
        main_logger.warning("Upload job: failed, will retry later.")


def webcam_job():
    t = threading.Thread(target=webcam.trigger, daemon=True)
    t.start()
    main_logger.info(f"Daily webcam capture triggered at {CAPTURE_TIME}.")


# --------------------
# Bootstrap
# --------------------
if __name__ == "__main__":
    try:
        main_logger.info(
            f"Delaying startup for {STARTUP_DELAY} seconds to allow time sync..."
        )
        time.sleep(STARTUP_DELAY)

        # 1) Discover devices (ports + samples)
        devs = discover_devices()
        roles = classify_roles(devs)  # [(role, port), ...]

        # 2) Start dedicated readers
        readers = []
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
        # Kick off an early upload ~60s after boot so first couple of samples get sent quickly
        schedule.every(30).seconds.do(aggregate_once)
        threading.Timer(60.0, upload_once).start()
        schedule.every(SCHEDULE_SECONDS).seconds.do(upload_once)
        schedule.every().day.at(CAPTURE_TIME).do(webcam_job)

        # 4) Main loop
        while True:
            schedule.run_pending()
            time.sleep(1)

    except Exception as e:
        main_logger.error(f"Fatal error in main: {e}")
