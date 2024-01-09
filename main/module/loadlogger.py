from utils.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class LoadLogger:
    def __init__(self, savepath):
        self.savepath = savepath

    def read(self):
        pass
