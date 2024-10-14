import os
import time

import schedule
from module.aws.apigateway import ApiGatewayConnector
from module.device import Device
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)

apigateway = ApiGatewayConnector(
    base_url=os.getenv("API_GATEWAY_MILJOSTASJON_URL"), api_key=os.getenv("API_GATEWAY_MILJOSTASJON_KEY")
)


# TODO: Add functinality for assuming the correct ttyUSB port based on expected input form the device
charger = Device(
    device_name="charger",
    baudrate=19200,
    timeout=3,
    serial_start="PID",
    serial_end="HSDS",
)

loadlogger = Device(
    device_name="loadlogger",
    baudrate=19200,
    timeout=3,
    serial_start="PID",
    serial_end="H18",
)


def read_and_send_data():
    charger.read_data()
    loadlogger.read_data()

    # Combine data and post
    data = {}
    data["charger"] = charger.data
    data["loadlogger"] = loadlogger.data

    # Post to endpoint for combined data
    try:
        apigateway.post_dict(
            endpoint="receive",
            data=data,
            payload_parent_keys={"deviceId": os.getenv("DEVICE_ID")},
        )

    except Exception:
        logger.info(
            "Error sending data: {e}. \n \n Retrying in 30 minutes or until reboot..."
        )
        time.sleep(1800)


if __name__ == "__main__":
    try:
        schedule.every(app_config.config["device"]["readfrequency_seconds"]).seconds.do(
            read_and_send_data
        )

        read_and_send_data()
        while True:
            schedule.run_pending()
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
