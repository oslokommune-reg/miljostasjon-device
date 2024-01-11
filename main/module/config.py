import os

import toml

from module.aws.apigateway import ApiGatewayConnector
from module.utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class AppConfig:
    def __init__(self):
        self.base_url = os.getenv("API_GATEWAY_MILJOSTASJON_URL")
        self.api_key = os.getenv("API_GATEWAY_MILJOSTASJON_KEY")
        self.device_id = os.getenv("DEVICE_ID")
        self.config = self.load_config()

    def load_config(self):
        try:
            apigateway = ApiGatewayConnector(
                base_url=self.base_url, api_key=self.api_key
            )
            response = apigateway.get_data(
                endpoint="device", query=f"deviceid={self.device_id}"
            )
            return toml.loads(response["config"])
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise


# def load_toml_from_string(toml_string):
#     return toml.loads(toml_string)
