from module.aws.apigateway import ApiGatewayConnector

base_url = "<someurl>"
api_key = "<somekey>"
payload_parent_keys = {"stationId": "5", "locationId": "1"}


data = {"key1": "value1", "key2": "value2"}

apigateway = ApiGatewayConnector(
    base_url=base_url, api_key=api_key, payload_parent_keys=payload_parent_keys
)

apigateway.post_dict(endpoint="charger", data=data)
