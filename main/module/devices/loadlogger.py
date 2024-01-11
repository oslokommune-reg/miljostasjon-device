from serial import Serial
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)

class Loadlogger:
    def __init__(self, port, baud_rate):
        self.ser = Serial(port, baud_rate, timeout=3)  # Åpner forbindelsen

    def __del__(self):
        self.ser.close()  # Lukker forbindelsen

    def read_data(self):
        data = {}
        collecting = False

        line = self.ser.readline().decode("latin-1").strip()
        if not line:  # Håndterer tomme linjer
            return None

        # Starter innsamling når 'PID' oppdages
        if 'PID' in line:
            collecting = True
            data = {}

        if collecting:
            # Splitter linjen i nøkkel og verdi
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                key, value = parts
                data[key.strip()] = value.strip()

            # Avslutter innsamling etter 'MON'
            if 'MON' in line:
                logger.info(f"Received data block: {data}")
                collecting = False
                
                return data
