from loguru import logger
from clean_parquetV2 import process_folder_to_geoparquet
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
    #path = directory containing the geojson files of the layers
    path = input("Provide the location of the directory containing the layers of the tehsil")

    process_folder_to_geoparquet(path)
