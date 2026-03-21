from sqlalchemy import Column, BigInteger, String, DateTime, Enum, Integer, JSON, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class TaskType(str, enum.Enum):
    FILTER_VOXEL = "filter_voxel"
    FILTER_STATISTICAL = "filter_statistical"
    SEGMENT_RANSAC = "segment_ransac"
    REGISTER_ICP = "register_icp"
    CONVERT_FORMAT = "convert_format"
    AI_DETECTION = "ai_detection"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    point_cloud_id = Column(BigInteger, ForeignKey("point_clouds.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(BigInteger, ForeignKey("scenes.id", ondelete="SET NULL"), index=True)
    task_type = Column(Enum(TaskType), nullable=False)
    task_name = Column(String(200))
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    priority = Column(Integer, default=5)
    parameters = Column(JSON, nullable=False)
    result_point_cloud_id = Column(BigInteger, ForeignKey("point_clouds.id", ondelete="SET NULL"))
    result_summary = Column(JSON)
    error_message = Column(Text)
    progress = Column(Float, default=0)
    worker_id = Column(String(100))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_duration = Column(Integer)
    actual_duration = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    point_cloud = relationship("PointCloud", foreign_keys=[point_cloud_id], back_populates="processing_tasks")
    user = relationship("User", back_populates="processing_tasks")
    scene = relationship("Scene", back_populates="processing_tasks")
    result_point_cloud = relationship("PointCloud", foreign_keys=[result_point_cloud_id], back_populates="result_tasks")
    
    def __repr__(self):
        return f"<ProcessingTask(id={self.id}, type={self.task_type}, status={self.status})>"
    
    def to_dict(self, include_point_cloud=False):
        data = {
            "id": self.id,
            "task_type": self.task_type.value if self.task_type else None,
            "task_name": self.task_name,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "progress": self.progress,
            "parameters": self.parameters,
            "result_summary": self.result_summary,
            "error_message": self.error_message,
            "point_cloud_id": self.point_cloud_id,
            "result_point_cloud_id": self.result_point_cloud_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "actual_duration": self.actual_duration,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_point_cloud and self.point_cloud:
            data["point_cloud"] = self.point_cloud.to_dict()
        
        if self.result_point_cloud:
            data["result_point_cloud"] = self.result_point_cloud.to_dict()
        
        return data
