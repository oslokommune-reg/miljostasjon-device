# main.py
# ------------------------------------------------------------
# Orchestrates discovery, continuous readers, aggregation and upload.
# - Readers continuously update an in-memory "latest_frames" map.
# - Aggregator (every 60s) snapshots latest frames (fresh enough) and
#   appends an entry to /container_storage/temporary_device_data.json.
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


# --------------------
# Jobs
# --------------------
def aggregate_once():
    """
    Snapshot latest frames and write one entry into the buffer.
    Include only roles with frames fresher than FRESHNESS_SECONDS.
    """
    now = datetime.now(get_localzone())
    now_iso = now.isoformat()

    entry = {"timestamp": now_iso}
    included = []

    # Copy keys to avoid concurrent modification during iteration
    for role in list(latest_frames.keys()):
        frame = latest_frames.get(role, {})
        ts = frame.get("_ts")
        if not ts:
            continue

        # Compute age
        try:
            from datetime import datetime as _dt

            last_dt = _dt.fromisoformat(ts)
            age = (now - last_dt).total_seconds()
        except Exception:
            age = FRESHNESS_SECONDS + 1

        if age <= FRESHNESS_SECONDS:
            # Copy without _ts for the output format
            clean = {k: v for k, v in frame.items() if k != "_ts"}
            entry[role] = clean
            included.append(role)

    if not included:
        main_logger.info("No fresh frames available for aggregation window; skipping.")
        return

    buffer.append(entry)
    main_logger.info(f"Aggregated entry with roles: {included}")


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
        # Kick off an early upload ~90s after boot so first couple of samples get sent quickly
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
