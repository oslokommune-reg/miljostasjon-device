from datetime import datetime, timezone
import platform

from serial import Serial
from tzlocal import get_localzone

from module.utils.logger import setup_custom_logger


class Device:
    def __init__(
        self,
        device_name,
        baudrate,
        timeout,
        serial_start,
        serial_end,
        vendor_id=None,
        product_id=None,
    ):
        self.device_name = device_name
        self.logger = setup_custom_logger(device_name)
        self.port = self.find_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_start = serial_start
        self.serial_end = serial_end
        self.logger.info(f"Device: {port} {baudrate} {timeout}")

    def find_port(self):
        potential_ports = self.list_potential_ports()
        for port in potential_ports:
            if self.verify_port(port):
                self.port = port
                self.logger.info(
                    f"Device {self.device_name} found on port: {self.port}"
                )
                return
        raise Exception(f"No matching port found for {self.device_name}")

    def list_potential_ports(self):
        if platform.system() == "Linux":
            import glob

            return glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        else:
            ports = list(list_ports.comports())
            return [
                port.device
                for port in ports
                if (self.vendor_id is None or port.vid == self.vendor_id)
                and (self.product_id is None or port.pid == self.product_id)
            ]

    def verify_port(self, port):
        try:
            with Serial(port, self.baudrate, timeout=self.timeout) as ser:
                start_time = time.time()
                while time.time() - start_time < 5:  # Try for 5 seconds
                    line = ser.readline().decode("latin-1").strip()
                    if self.serial_start in line and self.serial_end in line:
                        return True
            return False
        except Exception as e:
            self.logger.error(f"Error verifying port {port}: {e}")
            return False

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
            self.logger.info(f"Received line: {line}")

            if self.serial_start in line:
                collecting = True
                data = {}

            if collecting:
                if "checksum" in line.lower():
                    # Do not collect checksum lines
                    continue

                # logger.info("Collectig :)")
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    key, value = parts
                    data[key.strip()] = value.strip()

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
