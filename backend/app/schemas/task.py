from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskStatus, TaskType


class TaskCreateRequest(BaseModel):
    pointcloud_id: int
    task_type: TaskType
    parameters: dict = Field(default_factory=dict)
    output_format: str = Field(default="xyz")

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        allowed = {"xyz", "csv", "ply"}
        lower = value.lower()
        if lower not in allowed:
            raise ValueError(f"输出格式仅支持: {', '.join(sorted(allowed))}")
        return lower


class TaskListItem(BaseModel):
    id: int
    pointcloud_id: int
    task_type: TaskType
    parameters: dict | None
    status: TaskStatus
    result_pointcloud_id: int | None
    output_format: str
    error_message: str | None
    created_by: int
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class TaskCreateResponse(BaseModel):
    id: int
    status: TaskStatus
    message: str
