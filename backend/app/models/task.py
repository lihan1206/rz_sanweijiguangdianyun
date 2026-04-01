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
    VOXEL_GRID = "voxel_grid"
    STATISTICAL_OUTLIER = "statistical_outlier"
    RANSAC_PLANE = "ransac_plane"
    ICP_REGISTRATION = "icp_registration"
    VOXELIZATION = "voxelization"
    POISSON_RECONSTRUCTION = "poisson_reconstruction"
    MESHING = "meshing"


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pointcloud_id: Mapped[int] = mapped_column(ForeignKey("pointclouds.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("collaborative_sessions.id"))
    task_type: Mapped[TaskType] = mapped_column(SqlEnum(TaskType), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    result_pointcloud_id: Mapped[int | None] = mapped_column(ForeignKey("pointclouds.id"))
    output_format: Mapped[str] = mapped_column(String(16), default="xyz", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    pointcloud = relationship("PointCloud", foreign_keys=[pointcloud_id], back_populates="tasks")
    result_pointcloud = relationship("PointCloud", foreign_keys=[result_pointcloud_id])
    creator = relationship("User", back_populates="tasks")
