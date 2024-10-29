import os
import time

import schedule
from module.aws.apigateway import ApiGatewayConnector
from module.device import SerialDevice
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)

apigateway = ApiGatewayConnector(
    base_url=os.getenv("API_GATEWAY_MILJOSTASJON_URL"),
    api_key=os.getenv("API_GATEWAY_MILJOSTASJON_KEY"),
)


charger = SerialDevice(
    device_name="charger",
    baudrate=19200,
    timeout=3,
    serial_start="PID",
    serial_end="HSDS",
)

loadlogger = SerialDevice(
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


        # TODO: Add method for collecting data every N seconds and storing it to system storage
        # TODO: Remove file stored on system if API response is 200

    except Exception:
        logger.info(
            "Error sending data: {e}. \n \n Retrying in 30 minutes or until reboot..."
        )
        time.sleep(1800)


if __name__ == "__main__":
    try:

        # Run once on startup
        logger.info("Commencing initial run...")
        read_and_send_data()
        logger.info("Initial run completed.")

        logger.info("Commencing schedule...")
        schedule.every(int(os.getenv("SCHEDULE_SECONDS", 300))).seconds.do(
            read_and_send_data
        )

        while True:
            schedule.run_pending()
            time.sleep(1)

    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
