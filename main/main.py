from module.charger import Charger
from module.loadlogger import Loadlogger
import schedule
import time
import logging
import boto3
import os
import sys
from serial import Serial

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)

charger_port = 'COM12'
charger_baud_rate = 19200
loadlogger_port = 'COM12'
loadlogger_baud_rate = 19200
station_id = '1'


charger = Charger(port=charger_port, baud_rate=charger_baud_rate)
loadlogger = Loadlogger(port=loadlogger_port, baud_rate=loadlogger_baud_rate)

def scheduled_upload(savepath):
    #upload_to_lambda(savepath)
    logging.info("Scheduled upload to lambda")

if __name__ == "__main__":
    #schedule.every(1).minutes.do(charger.read_and_save_to_json)
    while True:
        logging.info(f"reading")

        with Serial(port, baud_rate, timeout=1) as ser:
            while True:
                data_block = Charger.read_data(ser)
                if data_block:
                    print(data_block)  # Printer ut den komplette datablokken
                else:
                    print("Ingen ny data mottatt.")
        time.sleep(10)
