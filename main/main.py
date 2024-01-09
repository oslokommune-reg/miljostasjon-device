from module.charger import Charger
#from module.loadlogger import LoadLogger
import schedule
import time
import logging
import boto3
import os
import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)

port = 'COM13'
baud_rate = 19200
station_id = '1'
savepath = "data"

charger = Charger(savepath=savepath, port=port, baud_rate=baud_rate, station_id=station_id)

def upload_to_lambda(savepath):
    lambda_client = boto3.client('lambda')
    for filename in os.listdir(savepath):
        with open(os.path.join(savepath, filename), 'rb') as f:
            # Her bør du implementere opplastingen til Lambda
            logging.info(f"File {filename} uploaded")
            os.remove(os.path.join(savepath, filename))

def scheduled_upload(savepath):
    #upload_to_lambda(savepath)
    logging.info("Scheduled upload to lambda")

if __name__ == "__main__":
    #schedule.every(1).minutes.do(charger.read_and_save_to_json)
    while True:

        logging.info(f"reading")
        charger.read_and_save_to_json()
        # schedule.run_pending()
        # scheduled_upload(savepath)
        time.sleep(10)
