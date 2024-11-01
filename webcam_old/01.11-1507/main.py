import fcntl
import json
import os
import threading
import time
from datetime import datetime, timedelta
from queue import Queue

import schedule
from module.device import SerialDevice, Webcam
from module.utils.logger import setup_custom_logger
from tzlocal import get_localzone

# Initialize loggers
main_logger = setup_custom_logger("main")
charger_logger = setup_custom_logger("charger")
loadlogger_logger = setup_custom_logger("loadlogger")
webcam_logger = setup_custom_logger("webcam")
# Instantiate webcam
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
# Instantiate serial device
serial_device = SerialDevice()
# Queue for handling data from devices
device_data_queue = Queue()

# Threshold for load current to trigger webcam
WEBCAM_TRIGGER_THRESHOLD = 10  # Watt
WEBCAM_COOLDOWN_MINUTES = 5  # Minutes before a new picture

last_webcam_trigger_time = datetime.min  # Initialize to a very old date


# Path to JSON files
TEMP_DATA_FILE_PATH = "temporary_device_data.json"

# Initialize JSON files if they don't exist
if not os.path.exists(TEMP_DATA_FILE_PATH):
    with open(TEMP_DATA_FILE_PATH, "w") as file:
        json.dump([], file)


def continuous_read():
    """
    Continuously read data from devices and append to a temporary JSON file.
    """
    devices = [charger, loadlogger]

    global last_webcam_trigger_time

    while True:
        threads = []
        for device in devices:
            thread = threading.Thread(
                target=serial_device.collect_device_data,
                args=(device, device_data_queue),
            )
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Prepare data entry for the temporary JSON file
        data_entry = {
            "charger": {},
            "loadlogger": {},
            "timestamp": datetime.now(get_localzone()).isoformat(),
        }

        # Extract data from the queue
        while not device_data_queue.empty():
            device_name, device_data = device_data_queue.get()
            if device_name == "charger":
                data_entry["charger"] = device_data
            elif device_name == "loadlogger":
                data_entry["loadlogger"] = device_data

        # Check if we need to trigger the webcam
        if (
            "P" in data_entry["loadlogger"]
            and data_entry["loadlogger"]["P"] > WEBCAM_TRIGGER_THRESHOLD
        ):
            current_time = datetime.now()
            if current_time - last_webcam_trigger_time > timedelta(
                minutes=WEBCAM_COOLDOWN_MINUTES
            ):
                webcam_logger.info("Threshold exceeded, triggering webcam...")
                webcam.trigger_webcam()
                last_webcam_trigger_time = current_time
            else:
                webcam_logger.info("Threshold exceeded, but cooldown is still active.")

        # Append collected data to temporary JSON file
        if (
            data_entry["charger"] or data_entry["loadlogger"]
        ):  # Only append if data is not empty
            with open(TEMP_DATA_FILE_PATH, "r+") as file:
                fcntl.flock(file, fcntl.LOCK_EX)
                try:
                    existing_data = json.load(file)
                except json.JSONDecodeError:
                    existing_data = []
                existing_data.append(data_entry)
                file.seek(0)
                json.dump(existing_data, file, indent=4)
                file.truncate()

        # Sleep for a short time before collecting data again
        time.sleep(1)  # Adjust the interval as needed


if __name__ == "__main__":
    try:
        # Testing webcam (as you previously intended)
        webcam_logger.info("Testing webcam...")
        webcam.trigger_webcam()

        # Start continuous data collection in a separate thread
        main_logger.info("Continuously collecting data from serial...")
        read_thread = threading.Thread(target=continuous_read)
        read_thread.daemon = True
        read_thread.start()

        # Schedule data sending
        main_logger.info("Commencing schedule to send data file...")
        schedule_seconds = int(os.getenv("SCHEDULE_SECONDS", 10))
        schedule.every(schedule_seconds).seconds.do(serial_device.send_power_data)

        while True:
            schedule.run_pending()
            time.sleep(1)

    except Exception as e:
        main_logger.error(f"Fatal error in main: {e}")
