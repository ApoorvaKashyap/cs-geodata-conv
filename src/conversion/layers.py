from loguru import logger

from src.app.models import LayerConversionRequest
from src.conversion.algos import mws

# from src.utils.rand_funcs import sim_work
from src.work.work_queue import lq


def handle_layers(request: LayerConversionRequest) -> dict:
    logger.info("Handling layers")
    tid = lq.enqueue(layer_conversion, request)
    return {
        "task_id": tid.id,
        "status": tid.get_status().name,
    }


def layer_conversion(request: LayerConversionRequest) -> None:
    logger.info("Converting layers to a different format")
    try:
        mws.clean_parquet(request.filepath)
    except Exception as e:
        logger.error(f"Error in layer conversion: {e}")
        raise
