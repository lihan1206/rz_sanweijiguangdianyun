from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from app.db.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingType(str, enum.Enum):
    FILTER = "filter"
    SEGMENT = "segment"
    REGISTER = "register"
    DOWNSAMPLE = "downsample"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    point_clouds = relationship("PointCloud", back_populates="owner", cascade="all, delete-orphan")
    processing_jobs = relationship("ProcessingJob", back_populates="owner", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


class PointCloud(Base):
    __tablename__ = "point_clouds"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # 字节
    file_format = Column(String(10), nullable=False)  # las, ply 等
    point_count = Column(Integer, nullable=True)
    
    # 点云元数据
    bbox_min_x = Column(Float, nullable=True)
    bbox_min_y = Column(Float, nullable=True)
    bbox_min_z = Column(Float, nullable=True)
    bbox_max_x = Column(Float, nullable=True)
    bbox_max_y = Column(Float, nullable=True)
    bbox_max_z = Column(Float, nullable=True)
    
    # 坐标系信息
    crs = Column(String(50), nullable=True)  # 坐标参考系统
    
    # 所有者
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("User", back_populates="point_clouds")
    
    # 状态
    is_processed = Column(Boolean, default=False, nullable=False)
    processed_file_path = Column(String(500), nullable=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    processing_jobs = relationship("ProcessingJob", back_populates="point_cloud", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<PointCloud(id={self.id}, name={self.name}, format={self.file_format})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "file_format": self.file_format,
            "point_count": self.point_count,
            "bbox": {
                "min": [self.bbox_min_x, self.bbox_min_y, self.bbox_min_z],
                "max": [self.bbox_max_x, self.bbox_max_y, self.bbox_max_z]
            } if self.bbox_min_x is not None else None,
            "crs": self.crs,
            "is_processed": self.is_processed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_name = Column(String(255), nullable=False)
    
    # 处理类型
    processing_type = Column(Enum(ProcessingType), nullable=False)
    
    # 状态
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True)
    
    # 进度 (0-100)
    progress = Column(Float, default=0.0, nullable=False)
    
    # 关联的点云
    point_cloud_id = Column(Integer, ForeignKey("point_clouds.id", ondelete="CASCADE"), nullable=False, index=True)
    point_cloud = relationship("PointCloud", back_populates="processing_jobs")
    
    # 所有者
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("User", back_populates="processing_jobs")
    
    # 处理参数
    parameters = Column(JSON, nullable=True)
    
    # 处理结果
    result_data = Column(JSON, nullable=True)
    result_file_path = Column(String(500), nullable=True)
    
    # 错误信息
    error_message = Column(Text, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 性能指标
    processing_duration = Column(Float, nullable=True)  # 秒
    
    def __repr__(self):
        return f"<ProcessingJob(id={self.id}, type={self.processing_type}, status={self.status})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "job_name": self.job_name,
            "processing_type": self.processing_type.value if self.processing_type else None,
            "status": self.status.value if self.status else None,
            "progress": self.progress,
            "point_cloud_id": self.point_cloud_id,
            "parameters": self.parameters,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "processing_duration": self.processing_duration
        }
