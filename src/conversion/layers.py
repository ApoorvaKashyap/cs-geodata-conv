from loguru import logger

from src.work.work_queue import lq


def handle_layers() -> dict:
    logger.info("Handling layers")
    tid = lq.enqueue(layer_conversion)
    return {
        "task_id": tid.id,
        "status": tid._status,
    }


def layer_conversion() -> None:
    logger.info("Converting layers to a different format")
