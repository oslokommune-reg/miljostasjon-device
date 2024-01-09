import json

import requests


class ApiGatewayConnector:
    def __init__(
        self, base_url: str, api_key: str, station_id: str, add_prefix: bool = True
    ) -> None:
        """
        Docstring documentation
        """
        self.base_url = base_url
        self.api_key = api_key

    def post_dict(self, endpoint: str, data: dict) -> None:
        requests.post(
            self.base_url + f"/{endpoint}",
            data=json.dumps(data),
            headers={"x-api-key": self.api_key},
        )

    def post_json(self, endpoint: str, data: dict) -> None:
        requests.post(
            self.base_url + f"/{endpoint}",
            data=json.dumps(data),
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )

    def get_data(self, endpoint: str, query: str) -> dict:
        response = requests.get(
            self.base_url + f"/{endpoint}?{query}",
            headers={"x-api-key": self.api_key},
        ).json()

        return response

    def _add_data_prefix(self):
        pass
