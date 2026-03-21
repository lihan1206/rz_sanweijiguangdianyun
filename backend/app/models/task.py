from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskType(str, Enum):
    DOWNSAMPLE = "downsample"
    DENOISE = "denoise"
    CLIP_Z = "clip_z"
    FORMAT_CONVERT = "format_convert"
    VOXEL_GRID_FILTER = "voxel_grid_filter"
    STATISTICAL_OUTLIER_REMOVAL = "statistical_outlier_removal"
    RANSAC_PLANE_SEGMENTATION = "ransac_plane_segmentation"
    ICP_REGISTRATION = "icp_registration"
    AI_OBJECT_DETECTION = "ai_object_detection"


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pointcloud_id: Mapped[int] = mapped_column(ForeignKey("pointclouds.id"), nullable=False)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("collaboration_scenes.id"))
    task_type: Mapped[TaskType] = mapped_column(SqlEnum(TaskType), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    result_pointcloud_id: Mapped[int | None] = mapped_column(ForeignKey("pointclouds.id"))
    output_format: Mapped[str] = mapped_column(String(16), default="ply", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    pointcloud = relationship("PointCloud", foreign_keys=[pointcloud_id], back_populates="tasks")
    result_pointcloud = relationship("PointCloud", foreign_keys=[result_pointcloud_id])
    creator = relationship("User", back_populates="tasks")
    scene = relationship("CollaborationScene", back_populates="tasks")
