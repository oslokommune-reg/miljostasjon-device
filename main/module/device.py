from datetime import datetime, timezone

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
        self.port = self.find_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_start = serial_start
        self.serial_end = serial_end
        self.logger = setup_custom_logger(device_name)
        self.logger.info(f"Device: {port} {baudrate} {timeout}")

    def find_port(self):
        if platform.system() == "Linux":
            return self.find_port_linux()
        else:
            return self.find_port_general()

    def find_port_linux(self):
        import glob

        ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if ports:
            return ports[0]  # Return the first found port
        else:
            raise Exception("No USB TTY port found")

    def find_port_general(self):
        ports = list(list_ports.comports())
        for port in ports:
            if self.vendor_id and self.product_id:
                if port.vid == self.vendor_id and port.pid == self.product_id:
                    return port.device
            elif self.device_name.lower() in port.description.lower():
                return port.device
        raise Exception(f"No matching port found for {self.device_name}")

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

            # Starter innsamling når 'PID' oppdages
            if self.serial_start in line:
                # self.logger.info("PID is in line")
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
