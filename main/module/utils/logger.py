import logging


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

    logger.setLevel(logging.DEBUG)
    return logger
