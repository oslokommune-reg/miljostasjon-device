import os

import toml
from module.aws.apigateway import ApiGatewayConnector

api_key = os.getenv("API_GATEWAY_MILJOSTASJON_KEY")
base_url = os.getenv("API_GATEWAY_MILJOSTASJON_URL")
device_id = os.getenv("DEVICE_ID")
payload_parent_keys = {"stationId": "0", "locationId": "1"}

print(api_key)
print(base_url)
print(payload_parent_keys)
print(device_id)

data = {"key1": "value1", "key2": "value2"}

apigateway = ApiGatewayConnector(base_url=base_url, api_key=api_key)

apigateway.post_dict(
    endpoint="charger", data=data, payload_parent_keys=payload_parent_keys
)
response = apigateway.get_data(endpoint="device", query=f"deviceid={device_id}")

toml_str = response["config"]

config = toml.loads(toml_str)

print(config["aws"])
