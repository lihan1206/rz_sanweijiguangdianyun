from sqlalchemy import Column, BigInteger, String, DateTime, Enum, Integer, JSON, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum
import secrets
import string


class SceneVisibility(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    SHARED = "shared"


class SceneMemberRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class Scene(Base):
    __tablename__ = "scenes"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    owner_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    visibility = Column(Enum(SceneVisibility), default=SceneVisibility.PRIVATE)
    max_members = Column(Integer, default=10)
    invite_code = Column(String(20), unique=True, index=True)
    settings = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="owned_scenes")
    members = relationship("SceneMember", back_populates="scene", cascade="all, delete-orphan")
    point_clouds = relationship("PointCloud", back_populates="scene")
    processing_tasks = relationship("ProcessingTask", back_populates="scene")
    
    def __repr__(self):
        return f"<Scene(id={self.id}, name={self.name}, owner_id={self.owner_id})>"
    
    def generate_invite_code(self):
        """生成邀请码"""
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(12))
    
    def to_dict(self, include_owner=False, include_stats=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "visibility": self.visibility.value if self.visibility else None,
            "max_members": self.max_members,
            "invite_code": self.invite_code,
            "settings": self.settings,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_owner and self.owner:
            data["owner"] = {
                "id": self.owner.id,
                "username": self.owner.username,
            }
        
        if include_stats:
            data["member_count"] = len(self.members) if self.members else 0
            data["point_cloud_count"] = len(self.point_clouds) if self.point_clouds else 0
        
        return data


class SceneMember(Base):
    __tablename__ = "scene_members"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scene_id = Column(BigInteger, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(SceneMemberRole), default=SceneMemberRole.VIEWER)
    permissions = Column(JSON)
    joined_at = Column(DateTime, server_default=func.now())
    last_active = Column(DateTime)
    
    # Relationships
    scene = relationship("Scene", back_populates="members")
    user = relationship("User", back_populates="scene_memberships")
    
    def __repr__(self):
        return f"<SceneMember(scene_id={self.scene_id}, user_id={self.user_id}, role={self.role})>"
    
    def to_dict(self, include_user=False):
        data = {
            "id": self.id,
            "scene_id": self.scene_id,
            "user_id": self.user_id,
            "role": self.role.value if self.role else None,
            "permissions": self.permissions,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }
        
        if include_user and self.user:
            data["user"] = {
                "id": self.user.id,
                "username": self.user.username,
                "full_name": self.user.full_name,
                "avatar_url": self.user.avatar_url,
            }
        
        return data
