from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UploadSession(Base):
    """分片上传会话"""
    __tablename__ = "upload_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    upload_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, uploading, completed, failed
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class UploadChunk(Base):
    """已上传的分片记录"""
    __tablename__ = "upload_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    upload_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    chunk_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(255), nullable=False)
    is_uploaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
