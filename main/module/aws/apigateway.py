import json

import requests


class ApiGatewayConnector:
    def __init__(self, base_url, api_key):
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

    def get_data(self, endpoint: str, query: str):
        response = requests.get(
            self.base_url + f"/{endpoint}?{query}",
            headers={"x-api-key": self.api_key},
        ).json()

        return response
