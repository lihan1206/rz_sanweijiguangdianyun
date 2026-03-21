from sqlalchemy import Column, BigInteger, String, DateTime, Enum, Integer, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class ChunkStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    MERGED = "merged"
    FAILED = "failed"


class FileChunk(Base):
    __tablename__ = "file_chunks"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    upload_id = Column(String(64), nullable=False, index=True)
    point_cloud_id = Column(BigInteger, ForeignKey("point_clouds.id", ondelete="SET NULL"), index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    chunk_path = Column(String(500))
    chunk_hash = Column(String(64))
    total_chunks = Column(Integer, nullable=False)
    status = Column(Enum(ChunkStatus), default=ChunkStatus.PENDING)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    point_cloud = relationship("PointCloud", back_populates="file_chunks")
    user = relationship("User", back_populates="file_chunks")
    
    def __repr__(self):
        return f"<FileChunk(upload_id={self.upload_id}, chunk_index={self.chunk_index})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "upload_id": self.upload_id,
            "chunk_index": self.chunk_index,
            "chunk_size": self.chunk_size,
            "total_chunks": self.total_chunks,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
