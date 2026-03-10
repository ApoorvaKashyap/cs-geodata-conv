from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI

from src.conversion.id import handle_id
from src.conversion.layers import handle_layers

app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    # Startup tasks
    yield
    # Shutdown tasks


@app.get(path="/")
async def read_root() -> dict[str, str]:
    return {"status": "ok"}


@app.post(path="/v1/layers")
def create_layer() -> dict[str, str]:
    return handle_layers()


@app.post(path="/v1/ids")
def create_mws() -> dict[str, str]:
    return handle_id()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0")
