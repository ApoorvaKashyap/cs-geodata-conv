import os
from os import PathLike

from loguru import logger


def iterate_local_files(dir_path: str | PathLike) -> dict[str, str]:
    files = {}
    try:
        for root, _, filenames in os.walk(dir_path):
            for filename in filenames:
                files[filename] = os.path.join(root, filename)
    except Exception as e:
        logger.error(f"Error iterating local files: {e}")
        raise
    return files
