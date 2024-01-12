from datetime import datetime, timezone

from serial import Serial
from tzlocal import get_localzone

from module.utils.logger import setup_custom_logger


class Device:
    def __init__(self, device_name, port, baudrate, timeout, serial_start, serial_end):
        self.device_name = device_name
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_start = serial_start
        self.serial_end = serial_end
        self.logger = setup_custom_logger(device_name)
        self.logger.info(f"Device: {port} {baudrate} {timeout}")

    def read_data(self):
        # Start with empty data
        data = {}
        try:
            self.ser = Serial(self.port, self.baudrate, timeout=self.timeout)
            self.logger.info("Serial port accessed.")
        except Exception as e:
            self.logger.error(f"Error loading serial: {e}")
            raise e

        # Set initial state of collecting to True
        reading = True
        collecting = False
        while reading:
            line = self.ser.readline().decode("latin-1").strip()
            # self.logger.info(f"Received line: {line}")

            # Starter innsamling når 'PID' oppdages
            if self.serial_start in line:
                # self.logger.info("PID is in line")
                collecting = True
                data = {}

            if collecting:
                # logger.info("Collectig :)")
                # Splitter linjen i nøkkel og verdi
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    key, value = parts
                    data[key.strip()] = value.strip()

                # Avslutter innsamling etter 'HSDS'
                if self.serial_end in line:
                    # Close
                    self.ser.close()
                    reading = False
                    collecting = False

                    # Add localtime to data
                    utc_dt = datetime.now(timezone.utc)
                    timestamp = utc_dt.astimezone(get_localzone()).isoformat()
                    data["timestamp"] = timestamp
                    self.logger.info(f"Received data block: {data}")
                    self.data = data
