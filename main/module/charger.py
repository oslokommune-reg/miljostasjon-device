import json
import os
from datetime import datetime

from dateutil import tz
from serial import Serial
from utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class Charger:
    def __init__(self, savepath, port, baud_rate, station_id):
        self.savepath = savepath
        self.port = port
        self.baud_rate = baud_rate
        self.station_id = station_id

    def read_data(ser):
        data = {}
        collecting = False

        while True:
            line = ser.readline().decode("latin-1").strip()

            # Sjekk for 'Checksum' som indikerer start/slutt på en data blokk
            if "Checksum" in line:
                if collecting:
                    # Returnerer data ved slutten av en komplett blokk
                    return data
                else:
                    # Starter innsamling for en ny blokk
                    collecting = True
                    data = {}
                    continue

            if collecting:
                # Behandler linjer innenfor en data blokk
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    key, value = parts
                    data[key.strip()] = value.strip()

        # Returnerer en tom dictionary som en sikkerhetsmekanisme
        return data
