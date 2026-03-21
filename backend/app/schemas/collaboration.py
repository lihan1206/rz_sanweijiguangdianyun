from datetime import datetime

from pydantic import BaseModel, Field


class SceneCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    max_users: int = Field(default=10, ge=1, le=100)
    settings: dict | None = None


class SceneUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    is_active: bool | None = None
    max_users: int | None = Field(None, ge=1, le=100)
    settings: dict | None = None


class ScenePointCloudAddRequest(BaseModel):
    pointcloud_id: int
    transform_matrix: dict | None = None
    visible: bool = True
    color: str | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ScenePointCloudUpdateRequest(BaseModel):
    transform_matrix: dict | None = None
    visible: bool | None = None
    color: str | None = None
    opacity: float | None = Field(None, ge=0.0, le=1.0)


class ScenePointCloudItem(BaseModel):
    id: int
    scene_id: int
    pointcloud_id: int
    pointcloud_name: str
    transform_matrix: dict | None
    visible: bool
    color: str | None
    opacity: float
    order: int
    added_by: int
    added_by_name: str
    added_at: datetime

    model_config = {"from_attributes": True}


class SessionInfo(BaseModel):
    id: int
    user_id: int
    username: str
    camera_position: dict | None
    camera_target: dict | None
    is_active: bool
    joined_at: datetime

    model_config = {"from_attributes": True}


class SceneDetail(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    max_users: int
    settings: dict | None
    created_by: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    pointclouds: list[ScenePointCloudItem]
    active_sessions: list[SessionInfo]

    model_config = {"from_attributes": True}


class SceneListItem(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    max_users: int
    created_by: int
    created_by_name: str
    created_at: datetime
    pointcloud_count: int
    active_users: int

    model_config = {"from_attributes": True}


class SceneCreateResponse(BaseModel):
    id: int
    message: str


class SceneJoinResponse(BaseModel):
    session_token: str
    scene: SceneDetail
    message: str


class CameraUpdateRequest(BaseModel):
    camera_position: dict
    camera_target: dict


class SceneEventMessage(BaseModel):
    event_type: str
    scene_id: int
    user_id: int
    username: str
    data: dict | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
