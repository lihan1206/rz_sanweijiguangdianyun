from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class ProcessingStatus(PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    point_clouds = relationship("PointCloud", back_populates="owner")
    processing_jobs = relationship("ProcessingJob", back_populates="user")

class PointCloud(Base):
    __tablename__ = "point_clouds"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    file_format = Column(String(10))
    point_count = Column(Integer)
    description = Column(Text)
    metadata = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="point_clouds")
    processing_jobs = relationship("ProcessingJob", back_populates="point_cloud")

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    operation_type = Column(String(100), nullable=False)
    parameters = Column(Text)
    result_path = Column(String(500))
    error_message = Column(Text)
    processing_time = Column(Float)
    point_count_before = Column(Integer)
    point_count_after = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"))
    point_cloud_id = Column(Integer, ForeignKey("point_clouds.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="processing_jobs")
    point_cloud = relationship("PointCloud", back_populates="processing_jobs")
