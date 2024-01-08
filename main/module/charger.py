import logging


class Charger:
    def __init__(self, savepath):
        self.savepath = savepath

    def read(self):
        logging.info(f"Read and wrote to json to {self.savepath}")

    def set_usb_source(self):
        logging.info(f"Set usb source to {self.savepath}")
