from loguru import logger

from src.utils.rand_funcs import sim_work
from src.work.work_queue import iq


def handle_id() -> dict:
    logger.info("Handling ids")
    tid = iq.enqueue(id_conversion)
    return {
        "task_id": tid.id,
        "status": tid._status,
    }


def id_conversion() -> None:
    logger.info("Converting ids to a different format")
    sim_work()
