from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CollaborativeSession(Base):
    __tablename__ = "collaborative_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    current_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    creator = relationship("User", foreign_keys=[created_by])
    participants = relationship("SessionParticipant", back_populates="session")
    pointclouds = relationship("PointCloud", back_populates="session")


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("collaborative_sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_active: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    session = relationship("CollaborativeSession", back_populates="participants")
    user = relationship("User")
