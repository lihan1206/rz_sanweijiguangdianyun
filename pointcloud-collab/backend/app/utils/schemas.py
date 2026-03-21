from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# ==================== 响应基类 ====================
class ResponseBase(BaseModel):
    code: int = 200
    message: str = "Success"
    data: Optional[Any] = None


class PaginatedResponse(ResponseBase):
    data: Dict[str, Any]


# ==================== 用户相关 ====================
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse


# ==================== 点云相关 ====================
class PointCloudStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class PointCloudVisibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    SCENE_ONLY = "scene_only"


class FileFormat(str, Enum):
    PLY = "ply"
    LAS = "las"
    LAZ = "laz"
    XYZ = "xyz"
    PCD = "pcd"
    OBJ = "obj"


class PointCloudBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    visibility: PointCloudVisibility = PointCloudVisibility.PRIVATE


class PointCloudCreate(PointCloudBase):
    scene_id: Optional[int] = None


class PointCloudUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    visibility: Optional[PointCloudVisibility] = None


class BoundingBox(BaseModel):
    min: List[float]
    max: List[float]


class PointCloudResponse(PointCloudBase):
    id: int
    user_id: int
    scene_id: Optional[int]
    original_filename: str
    file_format: FileFormat
    file_size: int
    point_count: Optional[int]
    bounding_box: Optional[BoundingBox]
    has_color: bool
    has_normal: bool
    status: PointCloudStatus
    version: int
    created_at: datetime
    updated_at: datetime
    owner: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class PointCloudListResponse(BaseModel):
    items: List[PointCloudResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PointCloudDataResponse(BaseModel):
    format: str
    point_count: int
    has_color: bool
    has_normal: bool
    bounding_box: BoundingBox
    points_url: str
    colors_url: Optional[str]
    preview_image: Optional[str]


class ExportRequest(BaseModel):
    format: Literal["ply", "obj", "xyz"]
    include_color: bool = True
    include_normal: bool = False
    transform: Optional[Dict[str, List[float]]] = None


class ExportResponse(BaseModel):
    task_id: int
    status: str
    download_url: Optional[str]


# ==================== 文件上传相关 ====================
class UploadInitRequest(BaseModel):
    file_name: str
    file_size: int
    chunk_size: int = 5 * 1024 * 1024  # 5MB
    name: str
    description: Optional[str] = None
    scene_id: Optional[int] = None
    visibility: PointCloudVisibility = PointCloudVisibility.PRIVATE


class UploadInitResponse(BaseModel):
    upload_id: str
    total_chunks: int
    chunk_size: int


class ChunkUploadResponse(BaseModel):
    chunk_index: int
    status: str


class MergeChunksRequest(BaseModel):
    upload_id: str


# ==================== 处理任务相关 ====================
class TaskType(str, Enum):
    FILTER_VOXEL = "filter_voxel"
    FILTER_STATISTICAL = "filter_statistical"
    SEGMENT_RANSAC = "segment_ransac"
    REGISTER_ICP = "register_icp"
    CONVERT_FORMAT = "convert_format"
    AI_DETECTION = "ai_detection"


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VoxelFilterParams(BaseModel):
    voxel_size: float = Field(0.05, gt=0)


class StatisticalFilterParams(BaseModel):
    nb_neighbors: int = Field(20, gt=0)
    std_ratio: float = Field(2.0, gt=0)


class RansacSegmentParams(BaseModel):
    distance_threshold: float = Field(0.01, gt=0)
    ransac_n: int = Field(3, gt=0)
    num_iterations: int = Field(1000, gt=0)


class IcpRegisterParams(BaseModel):
    target_point_cloud_id: int
    max_correspondence_distance: float = Field(0.05, gt=0)
    init_transform: Optional[List[List[float]]] = None
    max_iterations: int = Field(30, gt=0)


class TaskCreate(BaseModel):
    point_cloud_id: int
    task_type: TaskType
    task_name: Optional[str] = Field(None, max_length=200)
    parameters: Dict[str, Any]
    scene_id: Optional[int] = None
    priority: int = Field(5, ge=1, le=10)


class TaskResponse(BaseModel):
    id: int
    task_type: TaskType
    task_name: Optional[str]
    status: TaskStatus
    priority: int
    progress: float
    parameters: Dict[str, Any]
    result_summary: Optional[Dict[str, Any]]
    error_message: Optional[str]
    point_cloud_id: int
    result_point_cloud_id: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    actual_duration: Optional[int]
    created_at: datetime
    point_cloud: Optional[PointCloudResponse] = None
    result_point_cloud: Optional[PointCloudResponse] = None
    
    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ==================== 场景相关 ====================
class SceneVisibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    SHARED = "shared"


class SceneMemberRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class SceneBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    visibility: SceneVisibility = SceneVisibility.PRIVATE


class SceneCreate(SceneBase):
    max_members: int = Field(10, ge=1, le=50)


class SceneUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    visibility: Optional[SceneVisibility] = None
    max_members: Optional[int] = Field(None, ge=1, le=50)


class SceneResponse(SceneBase):
    id: int
    owner_id: int
    invite_code: str
    max_members: int
    created_at: datetime
    updated_at: datetime
    owner: Optional[Dict[str, Any]] = None
    member_count: Optional[int] = None
    point_cloud_count: Optional[int] = None
    
    class Config:
        from_attributes = True


class SceneListResponse(BaseModel):
    items: List[SceneResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SceneMemberResponse(BaseModel):
    id: int
    scene_id: int
    user_id: int
    role: SceneMemberRole
    permissions: Optional[Dict[str, Any]]
    joined_at: datetime
    last_active: Optional[datetime]
    user: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class JoinSceneRequest(BaseModel):
    invite_code: str


class ScenePointCloudResponse(BaseModel):
    id: int
    name: str
    owner: Dict[str, Any]
    status: PointCloudStatus
    transform: Dict[str, List[float]]
    visible: bool
    color: str


class ActiveUserResponse(BaseModel):
    id: int
    username: str
    cursor_position: Optional[List[float]]
    view_matrix: Optional[List[float]]


class SceneDataResponse(BaseModel):
    scene_id: int
    point_clouds: List[ScenePointCloudResponse]
    active_users: List[ActiveUserResponse]


# ==================== WebSocket 相关 ====================
class WSSceneJoin(BaseModel):
    scene_id: int


class WSUserViewUpdate(BaseModel):
    scene_id: int
    view_matrix: List[float]
    cursor_position: List[float]


class WSPointCloudTransform(BaseModel):
    scene_id: int
    point_cloud_id: int
    transform: Dict[str, List[float]]


class WSPointCloudVisibility(BaseModel):
    scene_id: int
    point_cloud_id: int
    visible: bool


# ==================== 错误响应 ====================
class ErrorDetail(BaseModel):
    field: Optional[str]
    message: str


class ErrorResponse(BaseModel):
    code: int
    message: str
    error_code: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    request_id: str


# ==================== 分页参数 ====================
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class PointCloudFilterParams(PaginationParams):
    status: Optional[PointCloudStatus] = None
    scene_id: Optional[int] = None
    search: Optional[str] = None
    sort_by: Literal["created_at", "updated_at", "name", "point_count"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


class TaskFilterParams(PaginationParams):
    status: Optional[TaskStatus] = None
    point_cloud_id: Optional[int] = None
    scene_id: Optional[int] = None
