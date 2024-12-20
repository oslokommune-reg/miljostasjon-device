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
WEBCAM_TRIGGER_THRESHOLD = 16  # Watt
# Define webcam delay as a global variable (in minutes)
webcam_delay = 30  # 30 minutes
webcam_trigger_time = None
last_webcam_trigger_time = datetime.min  # Initialize to a very old date

# Path to JSON file
TEMP_DATA_FILE_PATH = "/container_storage/temporary_device_data.json"

# Initialize JSON file if it doesn't exist
if not os.path.exists(TEMP_DATA_FILE_PATH):
    print(f"Creating file at {TEMP_DATA_FILE_PATH}")
    with open(TEMP_DATA_FILE_PATH, "w") as file:
        json.dump([], file)


def continuous_read():
    """
    Continuously read data from devices and append to a temporary JSON file.
    """
    global webcam_trigger_time, webcam_delay

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
            ):
                P_value = int(data_entry["loadlogger"]["P"])

                if P_value < -WEBCAM_TRIGGER_THRESHOLD:
                    current_time = datetime.now()

                    # If P goes below the threshold, reset the timer
                    webcam_trigger_time = current_time
                    webcam_logger.info(
                        f"Threshold exceeded (P = {P_value}), starting {webcam_delay}-minute timer."
                    )

                    # Check if the configured time has passed since the threshold was exceeded
                    if webcam_trigger_time and (
                        current_time - webcam_trigger_time
                    ) < timedelta(minutes=webcam_delay):
                        remaining_time = timedelta(minutes=webcam_delay) - (
                            current_time - webcam_trigger_time
                        )
                        remaining_minutes = remaining_time.seconds // 60
                        webcam_logger.info(
                            f"Time remaining until webcam trigger: {remaining_minutes}m"
                        )

                    elif webcam_trigger_time and (
                        current_time - webcam_trigger_time
                    ) >= timedelta(minutes=webcam_delay):
                        webcam_logger.info(
                            f"{webcam_delay} minutes passed since P threshold was exceeded, triggering webcam (P = {P_value})..."
                        )
                        try:
                            webcam.trigger_webcam()
                        except Exception as e:
                            webcam_logger.error(f"Failed to trigger webcam: {e}")
                        webcam_trigger_time = None  # Reset the trigger time to prevent further webcam triggers

        # Append collected data to the temporary JSON file regardless of the webcam trigger
        if data_entry["charger"] or data_entry["loadlogger"]:
            try:
                # Load existing data, append new entry, and write back
                with open(TEMP_DATA_FILE_PATH, "r+") as file:
                    try:
                        file.seek(0)
                        existing_data = json.load(file)
                    except json.JSONDecodeError:
                        existing_data = []  # File is empty or corrupted, start fresh

                    existing_data.append(data_entry)

                    # Rewrite file with updated data
                    file.seek(0)
                    json.dump(existing_data, file, indent=4)
                    file.truncate()
            except Exception as e:
                main_logger.error(f"Error while handling the file: {e}")

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
