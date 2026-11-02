# uploader.py
# ------------------------------------------------------------
# Sends buffered readings to the API in batches, oldest first.
# A batch is deleted from the buffer only after the API answers 200, so a
# power cut or network error at any point means the batch is sent again
# next time (at-least-once delivery), never lost.
# ------------------------------------------------------------

import os
import threading
import time
from typing import Optional

from module.aws.apigateway import ApiGatewayConnector
from module.storage import ReadingBuffer
from module.utils.logger import setup_custom_logger

log = setup_custom_logger("module.uploader")

# 100 entries = 50 minutes of data at one entry per 30 s. Keeps requests
# small, so a station that was offline for days catches up in steps
# instead of failing on one huge request.
BATCH_SIZE = 100


class Uploader:
    def __init__(self, buffer: ReadingBuffer, enabled: bool = True):
        self.buffer = buffer
        self.enabled = enabled
        self._running = threading.Lock()  # never run two uploads at once
        self._api = ApiGatewayConnector(
            base_url=os.getenv("API_GATEWAY_MILJOSTASJON_URL"),
            api_key=os.getenv("API_GATEWAY_MILJOSTASJON_KEY"),
        )
        self._device_id = os.getenv("DEVICE_ID")

    def upload_pending(self, deadline: Optional[float] = None) -> bool:
        """Upload batches until the buffer is empty, an error occurs, or the
        monotonic `deadline` passes. Returns True if the buffer was emptied."""
        if not self.enabled:
            log.info(f"Upload disabled; {self.buffer.count()} entries buffered.")
            return False
        if not self._running.acquire(blocking=False):
            log.info("Upload already running; skipping.")
            return False
        try:
            while True:
                batch = self.buffer.oldest(BATCH_SIZE)
                if not batch:
                    log.info("Nothing to upload.")
                    return True
                if deadline is not None and time.monotonic() >= deadline:
                    log.warning("Upload deadline reached; remaining entries kept.")
                    return False

                try:
                    resp = self._api.post_dict(
                        endpoint="power",
                        payload_parent_keys={"deviceId": self._device_id},
                        data=[entry for _, entry in batch],
                    )
                except Exception as e:
                    log.error(f"Upload failed: {e}")
                    return False

                if resp.status_code != 200:
                    log.error(f"Upload failed with status {resp.status_code}")
                    return False

                self.buffer.delete_through(batch[-1][0])
                log.info(f"Uploaded {len(batch)} entries (through seq {batch[-1][0]}).")
        finally:
            self._running.release()
