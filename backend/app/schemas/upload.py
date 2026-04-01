from datetime import datetime
from pydantic import BaseModel, Field


class UploadInitRequest(BaseModel):
    """初始化上传请求"""
    file_name: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小（字节）", gt=0)
    file_hash: str | None = Field(None, description="文件哈希值（MD5/SHA256）")
    chunk_size: int = Field(10 * 1024 * 1024, description="分片大小（字节）", ge=1 * 1024 * 1024)  # 最小1MB


class UploadInitResponse(BaseModel):
    """初始化上传响应"""
    upload_id: str
    chunk_size: int
    total_chunks: int
    status: str


class ChunkUploadResponse(BaseModel):
    """分片上传响应"""
    upload_id: str
    chunk_number: int
    uploaded: bool
    message: str


class UploadCompleteRequest(BaseModel):
    """完成上传请求"""
    upload_id: str
    file_hash: str | None = Field(None, description="最终文件哈希值用于校验")
    name: str = Field(..., description="点云名称")
    group_name: str | None = None
    tags: str | None = None
    capture_time: str | None = None
    sensor_model: str | None = None
    coordinate_system: str | None = None


class UploadStatusResponse(BaseModel):
    """上传状态响应"""
    upload_id: str
    file_name: str
    file_size: int
    total_chunks: int
    uploaded_chunks: int
    status: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}
