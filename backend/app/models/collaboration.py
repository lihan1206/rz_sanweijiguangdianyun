from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CollaborationScene(Base):
    __tablename__ = "collaboration_scenes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSON)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    creator = relationship("User", back_populates="scenes")
    scene_pointclouds = relationship("ScenePointCloud", back_populates="scene", cascade="all, delete-orphan")
    sessions = relationship("CollaborationSession", back_populates="scene", cascade="all, delete-orphan")
    tasks = relationship("ProcessingTask", back_populates="scene")


class ScenePointCloud(Base):
    __tablename__ = "scene_pointclouds"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("collaboration_scenes.id"), nullable=False)
    pointcloud_id: Mapped[int] = mapped_column(ForeignKey("pointclouds.id"), nullable=False)
    transform_matrix: Mapped[dict | None] = mapped_column(JSON)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    opacity: Mapped[float] = mapped_column(default=1.0, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    scene = relationship("CollaborationScene", back_populates="scene_pointclouds")
    pointcloud = relationship("PointCloud")
    adder = relationship("User")


class CollaborationSession(Base):
    __tablename__ = "collaboration_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("collaboration_scenes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    camera_position: Mapped[dict | None] = mapped_column(JSON)
    camera_target: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime)

    scene = relationship("CollaborationScene", back_populates="sessions")
    user = relationship("User", back_populates="sessions")
