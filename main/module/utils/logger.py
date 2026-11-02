import logging
import os

# INFO by default: container logs end up on the SD card, and DEBUG every
# 30 s is a large share of all writes. Set LOG_LEVEL=DEBUG when debugging.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_custom_logger(name):
    formatter = logging.Formatter(
        fmt="%(asctime)s \t %(levelname)s \t %(name)s \t %(message)s"
    )

    logger = logging.getLogger(name)

    # Ensure that we only add the handler if there are no existing handlers
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(LOG_LEVEL)
    return logger
