import schedule
import time
from module.utils.logger import setup_custom_logger
from module.charger import Charger
from module.loadlogger import Loadlogger
from module.aws.apigateway import ApiGatewayConnector

logger = setup_custom_logger(__name__)

charger_port = 'COM12'
charger_baud_rate = 19200
loadlogger_port = 'COM14'
loadlogger_baud_rate = 19200
station_id = '1'
base_url = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXX'
api_key = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXX'         

charger = Charger(port=charger_port, baud_rate=charger_baud_rate)
loadlogger = Loadlogger(port=loadlogger_port, baud_rate=loadlogger_baud_rate)
#apiGateway = ApiGatewayConnector(base_url = base_url, api_key = api_key, station_id=station_id)

def read_and_upload_data():
    logger.info("Reading data from charger...")
    data = charger.read_data()
    logger.info("Uploading data from charger...")
    #upload = apiGateway.post_dict(data, "charger")

    logger.info("Reading data from loadlogger...")
    data = loadlogger.read_data()
    logger.info("Uploading data from loadlogger...")
    #upload = apiGateway.post_dict(data, "charger")



    # logger.info("Reading data from loadlogger...")
    # data
    # logger.info("Uploading data to loadlogger...")
    # loadlogger.upload_data(data, station_id)
    # logger.info("Data uploaded successfully.")
    
   

if __name__ == "__main__":
    # Sette opp planen
    #schedule.every(1).minutes.do(read_and_upload_data)

    # Kjører planlagte oppgaver kontinuerlig
    while True:
        read_and_upload_data()
        #schedule.run_pending()
        time.sleep(10)  # Legg til en kort pause for å forhindre overbelastning av CPU