# device.py
# ------------------------------------------------------------
# Robust VE.Direct device discovery + continuous readers
# - Detects MPPTs and SmartShunt, classifies roles, and ensures
#   stable names based on SER# (lowest -> 'charger', next -> 'charger_2').
#   * SmartShunt is accepted even if SER# is missing (PID/signature).
#   * Chargers are accepted even if SER# is missing (logged warning).
#     For ordering, devices without SER# are sorted last (tie-breaker: port).
# - Each device has its own continuous reader thread.
# - Frames are parsed using 'Checksum' as the end-of-frame marker.
# - Each reader MERGES keys across multiple frames into a rolling snapshot,
#   so history fields (SmartShunt H17/H18, MPPT H19–H22) are reliably present.
# - A shared dict holds the latest merged snapshot per role (updated by readers,
#   consumed by main.py).
# - File buffer and upload are encapsulated in FileBuffer.
# ------------------------------------------------------------

import base64
import fcntl
import json
import os
import platform
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
from serial import Serial
from serial.tools import list_ports
from tzlocal import get_localzone

from module.aws.apigateway import ApiGatewayConnector
from module.utils.logger import setup_custom_logger

# --------------------
# Environment (kept) & constants (fixed)
# --------------------
apigateway_url = os.getenv("API_GATEWAY_MILJOSTASJON_URL")
apigateway_key = os.getenv("API_GATEWAY_MILJOSTASJON_KEY")
device_id = os.getenv("DEVICE_ID")

BUFFER_PATH = "/container_storage/temporary_device_data.json"  # single persisted file

# Serial defaults (fixed)
DEFAULT_BAUD = 19200
DEFAULT_TIMEOUT = 3  # seconds

# Probe window per port at startup (fixed)
PROBE_SECONDS = 30  # increase to 45 if a device needs longer to emit a full frame

# Freshness window used by aggregator to include a device into an entry (fixed)
FRESHNESS_SECONDS = 120  # seconds

# Webcam settings (fixed)
WEBCAM_PORT = 0
WARMUP_SECONDS = 10
TMP_FOLDER = "/tmp"

# PID hints (informational)
PID_TO_ROLE = {
    "0xA057": "charger",  # MPPT
    "0xA389": "loadlogger",  # SmartShunt
}

REQUIRED_KEYS = {
    "loadlogger": ("PID", "V", "I", "P", "SOC", "CE", "H17"),
    "charger": ("PID", "SER#", "V", "I", "VPV", "PPV", "H22"),
    "charger_2": ("PID", "SER#", "V", "I", "VPV", "PPV", "H22"),
}


# How long we keep individual merged keys before expiring them (set 0 to disable)
MERGE_KEY_TTL_SECONDS = 600  # 10 minutes

# Loggers
log = setup_custom_logger("module.device")
webcam_logger = setup_custom_logger("webcam")


# --------------------
# Webcam
# --------------------
class Webcam:
    def __init__(self, port: int = WEBCAM_PORT, tmp_folder: str = TMP_FOLDER):
        self.port = port
        self.tmp_folder = tmp_folder
        self.cap = None
        webcam_logger.info(f"Webcam initialized with port {self.port}.")

    def _init_camera(self) -> bool:
        if self.cap is not None:
            self.cap.release()
            cv2.destroyAllWindows()
            time.sleep(1)

        self.cap = cv2.VideoCapture(self.port)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"JPEG"))

        if not self.cap.isOpened():
            webcam_logger.error("Failed to open webcam.")
            return False
        return True

    def trigger(self):
        if not self._init_camera():
            return
        try:
            # Best-effort tuning
            for prop, val in [
                (cv2.CAP_PROP_AUTO_EXPOSURE, 0.75),
                (cv2.CAP_PROP_AUTO_WB, 1),
                (cv2.CAP_PROP_GAIN, -1),
            ]:
                try:
                    self.cap.set(prop, val)
                except Exception:
                    pass

            start = time.monotonic()
            last_frame = None
            while time.monotonic() - start < WARMUP_SECONDS:
                ok, frame = self.cap.read()
                if ok:
                    last_frame = frame

            ok, frame = self.cap.read()
            frame = frame if ok else last_frame
            if frame is None:
                webcam_logger.error("Failed to capture frame after warmup.")
                return

            path = self._save_image(frame)
            self._send_image(path)
        except Exception as e:
            webcam_logger.exception(f"Webcam error: {e}")
        finally:
            if self.cap is not None:
                self.cap.release()
                cv2.destroyAllWindows()
                webcam_logger.info("Webcam resources released.")

    def _save_image(self, image) -> str:
        if not os.path.exists(self.tmp_folder):
            os.makedirs(self.tmp_folder, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(self.tmp_folder, f"webcam_capture_{ts}.jpg")
        cv2.imwrite(path, image, [cv2.IMWRITE_JPEG_QUALITY, 100])
        webcam_logger.info(f"Image saved to {path}.")
        return path

    def _send_image(self, image_path: str):
        try:
            with open(image_path, "rb") as img_file:
                b64 = base64.b64encode(img_file.read()).decode("utf-8")
            resp = ApiGatewayConnector(
                base_url=apigateway_url, api_key=apigateway_key
            ).post_dict(
                endpoint="image",
                payload_parent_keys={"deviceId": device_id},
                data={"image": b64},
            )
            if resp.status_code == 200:
                webcam_logger.info("Image successfully sent to API.")
                try:
                    os.remove(image_path)
                except OSError:
                    pass
            else:
                webcam_logger.error(f"Failed to send image: status={resp.status_code}")
        except FileNotFoundError:
            webcam_logger.error(f"Image not found: {image_path}")


# --------------------
# File buffer manager
# --------------------
class FileBuffer:
    """Manages a JSON list buffer stored on disk with safe locking.
    Path is typically /container_storage/temporary_device_data.json
    """

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def append(self, entry: Dict) -> None:
        """Append one entry to the buffer file atomically with lock."""
        try:
            with open(self.path, "a+b") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    raw = f.read().decode("utf-8") or ""
                    if raw.strip():
                        data = json.loads(raw)
                        if not isinstance(data, list):
                            data = []
                    else:
                        data = []
                except json.JSONDecodeError:
                    data = []

                data.append(entry)

                f.seek(0)
                f.truncate(0)
                f.write(json.dumps(data, indent=4).encode("utf-8"))
                f.flush()
        except Exception as e:
            log.error(f"FileBuffer.append failed: {e}")

    def upload_and_clear(self) -> bool:
        """Upload the buffer to API and clear it only on success."""
        try:
            if not os.path.exists(self.path):
                log.info("Buffer file not found; nothing to upload.")
                return True

            with open(self.path, "r+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []

                if not data:
                    log.info("No data to send.")
                    return True

                resp = ApiGatewayConnector(
                    base_url=apigateway_url, api_key=apigateway_key
                ).post_dict(
                    endpoint="power",
                    payload_parent_keys={"deviceId": device_id},
                    data=data,
                )
                log.info(f"Upload status: {resp.status_code}")
                if resp.status_code == 200:
                    f.seek(0)
                    json.dump([], f, indent=4)
                    f.truncate()
                    log.info("Data successfully sent and cleared from buffer.")
                    return True
                else:
                    log.error(f"Upload failed with status: {resp.status_code}")
                    return False
        except Exception as e:
            log.error(f"FileBuffer.upload_and_clear failed: {e}")
            return False


# --------------------
# Device discovery
# --------------------
def _list_serial_ports() -> List[str]:
    """Linux: /dev/ttyUSB* and /dev/ttyACM*. Else: enumerate via pyserial."""
    if platform.system() == "Linux":
        import glob

        return sorted(set(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")))
    return [p.device for p in list(list_ports.comports())]


def _read_probe_frame(
    port: str, baud: int = DEFAULT_BAUD, timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, str]:
    """Probe a port for up to PROBE_SECONDS, accumulating any key/value pairs seen.
    Does NOT require seeing 'PID' to return data; this is robust for SmartShunt which
    often emits H1..H18 before the PID appears in a subsequent frame.
    """
    try:
        ser = Serial(port, baud, timeout=timeout)
        if not ser.isOpen():
            ser.open()

        sample: Dict[str, str] = {}
        start = time.time()

        while time.time() - start < PROBE_SECONDS:
            line = ser.readline().decode("latin-1", errors="ignore").strip()
            if not line:
                continue

            # Generic "KEY <space> VALUE" parsing
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()

                # Treat checksum as a frame boundary, but keep accumulating
                if k.lower().startswith("checksum"):
                    continue

                # Accumulate last-seen value per key
                sample[k] = v

        ser.close()
        return sample
    except Exception as e:
        log.error(f"Probe failed on {port}: {e}")
        return {}


def _is_shunt_signature(sample: Dict[str, str]) -> bool:
    """Return True if the sample looks like a SmartShunt/BMV frame."""
    pid = sample.get("PID")
    return (
        pid == "0xA389" or "BMV" in sample or {"SOC", "TTG", "CE"} <= set(sample.keys())
    )


def _is_charger_signature(sample: Dict[str, str]) -> bool:
    """Return True if the sample looks like a charger (MPPT)."""
    pid = sample.get("PID")
    return pid == "0xA057" or "HSDS" in sample or "MPPT" in sample or "PPV" in sample


def discover_devices() -> List[Tuple[str, Dict[str, str]]]:
    """Return list of (port, sample_dict) for devices we deem valid.

    Rules:
      - Accept SmartShunt even if SER# is missing (PID/signature is enough).
      - Accept chargers even if SER# is missing (logged warning).
        We need SER# for stable ordering; devices without SER# will be placed last.
    """
    found: List[Tuple[str, Dict[str, str]]] = []
    ports = _list_serial_ports()
    log.info(f"Probing ports: {ports}")

    for p in ports:
        log.info(f"Probing port {p}...")
        sample = _read_probe_frame(p)

        if not sample:
            log.debug(
                f"Skipping {p} (no data seen during probe). Keys={list(sample.keys())}"
            )
            continue

        if _is_shunt_signature(sample):
            # Accept shunt without PID or SER#
            found.append((p, sample))
            continue

        if _is_charger_signature(sample):
            if "SER#" not in sample:
                log.warning(
                    f"{p}: Charger detected but SER# missing in probe window; naming may be unstable."
                )
            found.append((p, sample))
            continue

        # Not recognized as shunt or charger
        log.debug(f"Skipping {p} (unknown signature). Keys={list(sample.keys())}")

    return found


def classify_roles(devices: List[Tuple[str, Dict[str, str]]]) -> List[Tuple[str, str]]:
    """
    Input: [(port, sample)]
    Output: [(role, port)] with role ∈ {'charger', 'charger_2', 'loadlogger'}
    Rules:
      - Identify SmartShunt by signature and assign 'loadlogger' (first one).
      - Remaining MPPTs: sort by SER#; lowest -> 'charger', next -> 'charger_2'.
        Devices without SER# are sorted last; tie-breaker is port name.
    """
    chargers: List[Tuple[str, str, str]] = []  # (ser or "", port, port_for_tie)
    shunt_port: Optional[str] = None

    for port, sample in devices:
        if _is_shunt_signature(sample) and shunt_port is None:
            shunt_port = port
            continue
        if _is_charger_signature(sample):
            ser = sample.get("SER#", "")
            chargers.append((ser, port, port))

    # Sort chargers: with SER# first (lexicographically), then no-SER# by port
    def _sort_key(item: Tuple[str, str, str]):
        ser, port, _ = item
        return (0, ser) if ser else (1, port)

    chargers_sorted = sorted(chargers, key=_sort_key)

    roles: List[Tuple[str, str]] = []
    if len(chargers_sorted) >= 1:
        roles.append(("charger", chargers_sorted[0][1]))
    if len(chargers_sorted) >= 2:
        roles.append(("charger_2", chargers_sorted[1][1]))
    if shunt_port:
        roles.append(("loadlogger", shunt_port))

    log.info(f"Detected roles: {roles}")
    return roles


# --------------------
# Continuous VE.Direct reader (merged snapshot)
# --------------------
class ReaderThread(threading.Thread):
    """
    Continuous VE.Direct reader for a single serial port.

    Strategy:
      - Start collecting when we see 'PID'
      - A 'Checksum' line marks end-of-frame
      - Each complete frame is parsed into a dict and then MERGED into a rolling 'merged' snapshot.
      - For each key, we also store a per-key timestamp (for optional TTL cleanup).
      - The public output (latest_frames[role]) is the merged snapshot + a transport timestamp '_ts'.
    """

    def __init__(
        self,
        role: str,
        port: str,
        latest_frames: Dict[str, Dict[str, str]],
        baud: int = DEFAULT_BAUD,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        super().__init__(daemon=True)
        self.role = role
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.latest_frames = latest_frames
        self.stop_event = threading.Event()
        self.logger = setup_custom_logger(role)

        # rolling merged snapshot + per-key timestamps
        self._merged: Dict[str, str] = {}
        self._merged_key_ts: Dict[str, float] = {}

        # cache required keys for this role
        self._required_keys = set(REQUIRED_KEYS.get(role, ()))

    def _now_iso(self) -> str:
        return datetime.now(get_localzone()).isoformat()

    def _now_ts(self) -> float:
        return time.time()

    def _merge_frame(self, frame: Dict[str, str]):
        """Merge observed keys from a complete frame into rolling snapshot."""
        ts = self._now_ts()
        for k, v in frame.items():
            self._merged[k] = v
            self._merged_key_ts[k] = ts

        # optional: expire stale keys
        if MERGE_KEY_TTL_SECONDS > 0:
            cutoff = ts - MERGE_KEY_TTL_SECONDS
            stale = [k for k, t in self._merged_key_ts.items() if t < cutoff]
            for k in stale:
                self._merged_key_ts.pop(k, None)
                self._merged.pop(k, None)

        # publish merged snapshot
        self.latest_frames[self.role] = {**self._merged, "_ts": self._now_iso()}

    def _frame_has_required(self) -> bool:
        """Check if merged snapshot satisfies role's must-have keys."""
        if not self._required_keys:
            return True
        snap_keys = set(self._merged.keys())
        return self._required_keys.issubset(snap_keys)

    def run(self):
        backoff = 0.5
        while not self.stop_event.is_set():
            try:
                ser = Serial(self.port, self.baud, timeout=self.timeout)
                if not ser.isOpen():
                    ser.open()

                collecting = False
                frame: Dict[str, str] = {}

                # publish any pre-existing merged snapshot (useful after restart)
                if self._merged:
                    self.latest_frames[self.role] = {
                        **self._merged,
                        "_ts": self._now_iso(),
                    }

                while not self.stop_event.is_set():
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("latin-1", errors="ignore").strip()
                    if not line:
                        continue

                    # Godta TAB eller SPACE mellom key og value
                    if "\t" in line:
                        parts = line.split("\t", maxsplit=1)
                    else:
                        parts = line.split(maxsplit=1)

                    # Start en ny frame enten når vi ser PID
                    # ELLER når vi ser første gyldige key/value (history-frame uten PID)
                    if line.startswith("PID") or (
                        not collecting
                        and len(parts) == 2
                        and parts[0]
                        and parts[0].lower() != "checksum"
                    ):
                        collecting = True
                        frame = {}

                    if not collecting:
                        continue

                    if len(parts) == 2:
                        k, v = parts[0].strip(), parts[1].strip()

                        # Slutt på frame: Checksum
                        if k.lower().startswith("checksum"):
                            collecting = False
                            if frame:
                                self._merge_frame(
                                    frame
                                )  # MERGE selv om frame ikke har PID
                            frame = {}
                            continue

                        # Vanlig key/value
                        frame[k] = v

                ser.close()
                backoff = 0.5  # reset after a successful session
            except Exception as e:
                self.logger.error(f"I/O error on {self.port}: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def stop(self):
        self.stop_event.set()
