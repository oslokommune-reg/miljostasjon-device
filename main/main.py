import os
import time

import schedule
import toml
from module.aws.apigateway import ApiGatewayConnector
from module.config import AppConfig
from module.devices.charger import Charger
from module.devices.loadlogger import Loadlogger
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


def create_devices(config):
    charger = Charger(
        port=config["charger"]["usb_port"], baud_rate=config["charger"]["baud_rate"]
    )
    loadlogger = Loadlogger(
        port=config["loadlogger"]["usb_port"],
        baud_rate=config["loadlogger"]["baud_rate"],
    )
    return charger, loadlogger


def read_and_upload_data(charger, loadlogger, apigateway, config):
    try:
        for device, endpoint in [(charger, "charger"), (loadlogger, "loadlogger")]:
            logger.info(f"Reading data from {endpoint}...")
            data = device.read_data()
            logger.info(f"Uploading data from {endpoint}...")
            apigateway.post_dict(
                endpoint=endpoint,
                data=data,
                payload_parent_keys={"stationId": config["device"]["stationid"]},
            )
    except Exception as e:
        logger.error(f"Encountered error in read_and_upload_data: {e}")


if __name__ == "__main__":
    try:
        app_config = AppConfig()
        apigateway = ApiGatewayConnector(
            base_url=app_config.base_url, api_key=app_config.api_key
        )
        charger, loadlogger = create_devices(app_config.config)

        schedule.every(app_config.config["device"]["readfrequency_seconds"]).seconds.do(
            read_and_upload_data, charger, loadlogger, apigateway, app_config.config
        )

        while True:
            schedule.run_pending()
            time.sleep(1)
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
