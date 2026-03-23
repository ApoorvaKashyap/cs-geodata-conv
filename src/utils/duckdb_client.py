import duckdb
from duckdb import DuckDBPyConnection

from src.utils.configs import settings


class DuckDBClient:
    conn: DuckDBPyConnection = None

    def __init__(
        self, type: str = settings.duckdb_type, db_path: str = settings.duckdb_path
    ) -> None:
        match type:
            case "memory":
                self.conn = duckdb.connect(":memory:")
            case "file":
                self.conn = duckdb.connect(db_path)
            case _:
                raise ValueError(f"Invalid type: {type}")
        for ext in settings.duckdb_extensions:
            self.conn.install_extension(ext)
            self.conn.load_extension(ext)

    def __enter__(self) -> DuckDBPyConnection:
        if self.conn is None:
            self.__init__()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.conn.close()
