from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Enum, Integer, JSON, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class PointCloudStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class PointCloudVisibility(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    SCENE_ONLY = "scene_only"


class FileFormat(str, enum.Enum):
    PLY = "ply"
    LAS = "las"
    LAZ = "laz"
    XYZ = "xyz"
    PCD = "pcd"
    OBJ = "obj"


class PointCloud(Base):
    __tablename__ = "point_clouds"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(BigInteger, ForeignKey("scenes.id", ondelete="SET NULL"), index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    file_format = Column(Enum(FileFormat), nullable=False)
    file_hash = Column(String(64))
    point_count = Column(BigInteger)
    bounding_box = Column(JSON)  # {min: [x,y,z], max: [x,y,z]}
    has_color = Column(Boolean, default=False)
    has_normal = Column(Boolean, default=False)
    coordinate_system = Column(String(50))
    status = Column(Enum(PointCloudStatus), default=PointCloudStatus.UPLOADING, index=True)
    visibility = Column(Enum(PointCloudVisibility), default=PointCloudVisibility.PRIVATE)
    version = Column(Integer, default=1)
    parent_id = Column(BigInteger, ForeignKey("point_clouds.id", ondelete="SET NULL"))
    metadata = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="point_clouds")
    scene = relationship("Scene", back_populates="point_clouds")
    parent = relationship("PointCloud", remote_side=[id], backref="versions")
    processing_tasks = relationship("ProcessingTask", foreign_keys="ProcessingTask.point_cloud_id", back_populates="point_cloud")
    result_tasks = relationship("ProcessingTask", foreign_keys="ProcessingTask.result_point_cloud_id", back_populates="result_point_cloud")
    file_chunks = relationship("FileChunk", back_populates="point_cloud")
    
    def __repr__(self):
        return f"<PointCloud(id={self.id}, name={self.name}, status={self.status})>"
    
    def to_dict(self, include_owner=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "file_format": self.file_format.value if self.file_format else None,
            "file_size": self.file_size,
            "point_count": self.point_count,
            "status": self.status.value if self.status else None,
            "visibility": self.visibility.value if self.visibility else None,
            "has_color": self.has_color,
            "has_normal": self.has_normal,
            "bounding_box": self.bounding_box,
            "coordinate_system": self.coordinate_system,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_owner and self.owner:
            data["owner"] = {
                "id": self.owner.id,
                "username": self.owner.username,
            }
        
        return data
