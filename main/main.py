import fcntl
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Queue

import schedule
from module.device import SerialDevice, Webcam
from module.utils.logger import setup_custom_logger
from tzlocal import get_localzone

# Initialize loggers with proper levels
main_logger = setup_custom_logger("main")
charger_logger = setup_custom_logger("charger")
loadlogger_logger = setup_custom_logger("loadlogger")
webcam_logger = setup_custom_logger("webcam")

# Instantiate devices
webcam = Webcam()
charger = SerialDevice(
    device_name="charger",
    baudrate=19200,
    timeout=3,
    serial_start="PID",
    serial_end="HSDS",
)
loadlogger = SerialDevice(
    device_name="loadlogger",
    baudrate=19200,
    timeout=3,
    serial_start="PID",
    serial_end="H18",
)

devices = [charger, loadlogger]
device_data_queue = Queue()

# Thresholds for load current to trigger webcam
WEBCAM_TRIGGER_THRESHOLD = 10  # Watt
WEBCAM_COOLDOWN_MINUTES = 1  # Minutes before a new picture
last_webcam_trigger_time = datetime.min  # Initialize to a very old date

# Path to JSON file
TEMP_DATA_FILE_PATH = "temporary_device_data.json"

# Initialize JSON file if it doesn't exist
if not os.path.exists(TEMP_DATA_FILE_PATH):
    with open(TEMP_DATA_FILE_PATH, "w") as file:
        json.dump([], file)


def continuous_read():
    """
    Continuously read data from devices and append to a temporary JSON file.
    """
    global last_webcam_trigger_time

    while True:
        # Start threads for each device
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(device.collect_device_data, device, device_data_queue)
                for device in devices
            ]
            for future in futures:
                future.result()  # Block until each thread is complete

        # Prepare data entry for the temporary JSON file
        data_entry = {
            "charger": {},
            "loadlogger": {},
            "timestamp": datetime.now(get_localzone()).isoformat(),
        }

        # Extract data from the queue
        while not device_data_queue.empty():
            device_name, device_data = device_data_queue.get()
            data_entry[device_name] = device_data

        # Check if we need to trigger the webcam
        if (
            "P" in data_entry["loadlogger"]
            and data_entry["loadlogger"]["P"].lstrip("-").isdigit()
            and int(data_entry["loadlogger"]["P"]) < -WEBCAM_TRIGGER_THRESHOLD
        ):
            current_time = datetime.now()
            if (
                current_time - last_webcam_trigger_time
            ).total_seconds() > WEBCAM_COOLDOWN_MINUTES * 60:
                webcam_logger.info("Threshold exceeded, triggering webcam...")
                try:
                    webcam.trigger_webcam()
                except Exception as e:
                    webcam_logger.error(f"Failed to trigger webcam: {e}")
                last_webcam_trigger_time = current_time
            else:
                webcam_logger.debug("Threshold exceeded, but cooldown is still active.")
        # Append collected data to the temporary JSON file
        if data_entry["charger"] or data_entry["loadlogger"]:
            try:
                with open(TEMP_DATA_FILE_PATH, "r+") as file:
                    fcntl.flock(file, fcntl.LOCK_EX)
                    existing_data = json.load(file) if file.tell() > 0 else []
                    existing_data.append(data_entry)
                    file.seek(0)
                    json.dump(existing_data, file, indent=4)
                    file.truncate()
            except json.JSONDecodeError:
                main_logger.error("Failed to decode JSON data from file.")

        # Sleep before collecting data again
        time.sleep(1)


if __name__ == "__main__":
    try:
        # Testing webcam functionality
        webcam_logger.info("Testing webcam...")
        try:
            webcam.trigger_webcam()
        except Exception as e:
            webcam_logger.error(f"Failed to trigger webcam during test: {e}")

        # Start continuous data collection in a separate thread
        main_logger.info("Continuously collecting data from serial devices...")
        read_thread = threading.Thread(target=continuous_read)
        read_thread.daemon = True
        read_thread.start()

        # Schedule data sending
        main_logger.info("Commencing schedule to send data file...")
        schedule_seconds = int(os.getenv("SCHEDULE_SECONDS", 300))
        schedule.every(schedule_seconds).seconds.do(
            lambda: SerialDevice.send_power_data(TEMP_DATA_FILE_PATH)
        )

        while True:
            schedule.run_pending()
            time.sleep(1)

    except Exception as e:
        main_logger.error(f"Fatal error in main: {e}")
