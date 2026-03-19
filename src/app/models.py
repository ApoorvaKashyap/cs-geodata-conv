from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, DirectoryPath, Field


class column_mapping(BaseModel):
    drop_columns: list[str] = Field(description="The list of columns to drop")
    rename_columns: dict[str, str] = Field(
        description="The mapping of columns to rename"
    )


class LayerConversionRequest(BaseModel):
    unit: Literal["mws", "farms"] = Field(description="The basic unit of the data.")
    location: (
        DirectoryPath | Annotated[str, Query(pattern="^s3://([^/]+)/(.*?([^/]+)/?)$")]
    ) = Field(description="The location of the layers to convert.", default="")
    output_path: (
        DirectoryPath
        | Annotated[str, Query(pattern="^s3://([^/]+)/(.*?([^/]+)/?)$")]
        | None
    ) = Field(description="The location to save the converted layers.", default=None)
    layers: set[str] = Field(description="The set of layers to convert.", default=set())
    column_map: dict[str, column_mapping] = Field(
        description="The column mapping for each layer.", default_factory=dict
    )
    common_columns: list[str] = Field(
        description="The list of common columns.", default_factory=list
    )
    parquet_version: float = Field(
        description="The version of Parquet to use.", default=1.0
    )
    use_previous_mapping: bool = Field(
        description="Whether to use the previously provided column mapping.",
        default=False,
    )


class IDConversionRequest(BaseModel):
    type: str
    id_list: list[str]
    layers: list[str]
