import os

from duckdb import DuckDBPyConnection
from loguru import logger


def load_geofile(con: DuckDBPyConnection, geofile: str):
    pass


def base_layer(con: DuckDBPyConnection, base_layer: str, unit: str):
    with con:
        con.execute(f"CREATE TABLE {base_layer} from ST_READ('{base_layer}');")


def parquet_export(con: DuckDBPyConnection, table_name: str, output_path: str) -> None:
    try:
        logger.info(f"Exporting table {table_name} to {output_path}")
        con.execute(f"COPY {table_name} TO '{output_path}' (FORMAT PARQUET)")
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(
            f"Exported table {table_name} to {output_path} with file size: {file_size:.2f} MB"
        )
    except Exception as e:
        logger.error(f"Failed to export table {table_name} to {output_path}: {e}")
        raise
