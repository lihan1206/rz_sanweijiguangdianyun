from datetime import datetime

from pydantic import BaseModel, Field


class PointCloudListItem(BaseModel):
    id: int
    name: str
    original_filename: str
    file_format: str
    file_size: int
    points_count: int | None
    group_name: str | None
    tags: list[str] | None
    version: int
    is_archived: bool
    is_deleted: bool
    capture_time: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PointCloudDetail(PointCloudListItem):
    storage_path: str
    sensor_model: str | None
    coordinate_system: str | None
    bounding_box: dict | None
    created_by: int
    updated_at: datetime
    deleted_at: datetime | None


class PointCloudStats(BaseModel):
    total_points: int
    density_estimate: float
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    z_range: tuple[float, float]


class PointSample(BaseModel):
    points: list[list[float]]


class UploadResponse(BaseModel):
    id: int
    message: str


class RestoreResponse(BaseModel):
    message: str


class DeleteResponse(BaseModel):
    message: str
