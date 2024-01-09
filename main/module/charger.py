import json
from datetime import datetime
from dateutil import tz
import logging
from serial import Serial 
import os
logging.getLogger().addHandler(logging.StreamHandler())


class Charger:
    def __init__(self, savepath, port, baud_rate, station_id):
        self.savepath = savepath
        self.port = port
        self.baud_rate = baud_rate
        self.station_id = station_id

    def read_and_save_to_json(self):
        data = {}
        oslo = tz.gettz('Europe/Oslo')
        now = datetime.now(oslo)
        timestamp = now.strftime('%Y%m%dT%H%M%S%z')

        if not os.path.exists(self.savepath):
            os.makedirs(self.savepath)

        # Bygger filstien på en plattformuavhengig måte
        filename = os.path.join(self.savepath, f"{timestamp}.json")

        try:
            with Serial(self.port, self.baud_rate, timeout=1) as ser:
                logging.info(f"Reading")
                while ser.in_waiting:
                    line = ser.readline().decode('latin-1').strip()
                    if ":" in line:
                        key, value = line.split(":")
                        data[key] = value
                        logging.info(f"Reading data from charger: {data}")
                        print(data)

            with open(filename, "w") as f:
                json.dump(data, f)
                logging.info(f"Read data and saved to {filename}")
        except Exception as e:
            logging.error(f"Error reading from charger: {e}")
