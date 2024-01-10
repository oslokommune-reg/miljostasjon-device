import schedule
import time
from module.utils.logger import setup_custom_logger
from module.charger import Charger
from module.loadlogger import Loadlogger
from module.aws.apigateway import ApiGatewayConnector

logger = setup_custom_logger(__name__)

charger_port = '/dev/ttyUSB0'
charger_baud_rate = 19200
loadlogger_port = '/dev/ttyUSB1'
loadlogger_baud_rate = 19200
base_url = "https://n7qaee0st5.execute-api.eu-west-1.amazonaws.com/dev"
api_key = "3rveWx1PZyaVDY99hmU159qDGtRaUlhx5lR8oqz5"
payload_parent_keys = {"stationId": "1"}

charger = Charger(port=charger_port, baud_rate=charger_baud_rate)
loadlogger = Loadlogger(port=loadlogger_port, baud_rate=loadlogger_baud_rate)
apigateway = ApiGatewayConnector(base_url = base_url, api_key = api_key, payload_parent_keys=payload_parent_keys)

def read_and_upload_data():
    logger.info("Reading data from charger...")
    data = charger.read_data()
    logger.info("Uploading data from charger...")
    apigateway.post_dict(endpoint="charger", data=data)

    logger.info("Reading data from loadlogger...")
    data = loadlogger.read_data()
    logger.info("Uploading data from loadlogger...")
    apigateway.post_dict(endpoint="loadlogger", data=data)


    
   

if __name__ == "__main__":
    # Sette opp planen
    #schedule.every(1).minutes.do(read_and_upload_data)

    # Kjører planlagte oppgaver kontinuerlig
    while True:
        read_and_upload_data()
        #schedule.run_pending()
        time.sleep(10)  # Legg til en kort pause for å forhindre overbelastning av CPU