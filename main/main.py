from module.charger import Charger
from module.loadlogger import LoadLogger

charger_config = {"savepath": "somepath", "usb_port": "someport"}

charger = Charger(savepath="data/charger.json")

charger.read_and_save_to_json()
