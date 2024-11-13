from datetime import datetime, timezone

import requests
from tzlocal import get_localzone

from module.utils.logger import setup_custom_logger

# from utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class ApiGatewayConnector:
    def __init__(self, base_url: str, api_key: str) -> None:
        """
        Initializes the API Gateway Connector.

        Args:
        base_url (str): The base URL for the API.
        api_key (str): The API key for authentication.
        station_id (str): The ID of the station to be included in requests.
        """

        self.base_url = base_url
        self.api_key = api_key

    def post_dict(
        self, endpoint: str, data: dict, payload_parent_keys: dict = {}
    ) -> dict:
        """
        Performs a POST request with a dictionary. Data is automatically serialzied to JSON.

        Args:
        endpoint (str): The endpoint to add to the base url
        data (dict): The data as dictionary format

        Returns:
        dict: The response from the server
        """

        payload = self._construct_payload(payload_parent_keys)
        payload["data"] = data

        # logger.info(f"Performing POST request to {endpoint} with payload {payload}")
        response = requests.post(
            self.base_url + f"/{endpoint}",
            json=payload,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )

        logger.info(f"Response status code: {response.status_code}")

        return response

    def post_json(self, endpoint: str, data: dict) -> dict:
        """
        Sends a POST request with JSON.

        Args:
        endpoint (str): The API endpoint to which the request is sent.
        data (dict): The data to be sent in the request.

        Returns:
        dict: The response from the server.
        """

        payload = self._construct_payload()
        payload["data"] = data

        logger.info(f"Performing POST request to {endpoint} with payload {payload}")

        response = requests.post(
            self.base_url + f"/{endpoint}",
            data=payload,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )

        logger.info(f"Response status code: {response.status_code}")

        return response

    def get_data(self, endpoint: str, query: str) -> dict:
        """Performs a GET request to an endpoint, with a query string

        Args:
            endpoint (str): The endpoint to add to the base url
            query (str): The query to add to the get request, e.g. deviceid=5&location=1

        Returns:
            dict: The data returne from the request
        """

        url = self.base_url + f"/{endpoint}?{query}"

        logger.info(f"Performing GET request to {url}")

        response = requests.get(
            url,
            headers={"x-api-key": self.api_key},
        )

        logger.info(f"Response status code: {response.status_code}")

        data = response.json()

        return data

    def _construct_payload(self, payload_parent_keys):
        """
        Adds a timestamp and station ID to the request data.

        Args:
        data (dict): The original data for the request.

        Returns:
        dict: The modified data with added timestamp and station ID.
        """
        payload = {}
        if payload_parent_keys:
            for key, value in payload_parent_keys.items():
                payload[key] = value

        # Get local timestamp with timezone
        utc_dt = datetime.now(timezone.utc)
        timestamp = utc_dt.astimezone(get_localzone()).isoformat()
        payload["timestamp"] = timestamp

        return payload
