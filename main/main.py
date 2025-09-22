import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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


# Instantiate devices with the serial_start and serial_end arguments.
# serial_start and serial_end are used to identify which port to listen to, and to chunk the data into the correct "blocks" of data
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

# Path to JSON file
TEMP_DATA_FILE_PATH = "/container_storage/temporary_device_data.json"
# Constants for scheduling picture
CAPTURE_TIME = "21:10"  # Daily capture time (HH:MM, 24h format)

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
        time.sleep(60)


def capture_job():
    t = threading.Thread(target=webcam.trigger_webcam, daemon=True)
    t.start()
    main_logger.info(f"Scheduled webcam capture triggered ({CAPTURE_TIME}).")


if __name__ == "__main__":
    try:
        # Start continuous data collection in a separate thread
        main_logger.info("Continuously collecting data from serial devices...")
        read_thread = threading.Thread(target=continuous_read)
        read_thread.daemon = True
        read_thread.start()

        # Schedule one-time data send after 60 seconds
        def send_initial_data():
            main_logger.info("Sending initial data package after 1 minute...")
            SerialDevice.send_power_data(TEMP_DATA_FILE_PATH)

        initial_send_timer = threading.Timer(60.0, send_initial_data)
        initial_send_timer.start()

        # Schedule regular data sending
        main_logger.info("Commencing schedule to send data file...")
        schedule_seconds = int(os.getenv("SCHEDULE_SECONDS", 300))
        schedule.every(schedule_seconds).seconds.do(
            lambda: SerialDevice.send_power_data(TEMP_DATA_FILE_PATH)
        )
        # Schedule picture taken and sent to API
        schedule.every().day.at(CAPTURE_TIME).do(capture_job)

        while True:
            schedule.run_pending()
            time.sleep(1)

    except Exception as e:
        main_logger.error(f"Fatal error in main: {e}")
