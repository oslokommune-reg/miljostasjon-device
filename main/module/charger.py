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

    def read_data(ser):
        data = {}
        collecting = False

        while True:
            line = ser.readline().decode('latin-1').strip()

            # Sjekk for 'Checksum' som indikerer start/slutt på en data blokk
            if 'Checksum' in line:
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
