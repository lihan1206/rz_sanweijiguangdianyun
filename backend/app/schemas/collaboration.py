from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CollaborativeSessionBase(BaseModel):
    session_name: str = Field(..., min_length=2, max_length=128, description="会话名称")
    description: Optional[str] = Field(None, max_length=512, description="会话描述")
    max_users: Optional[int] = Field(10, ge=2, le=50, description="最大用户数")


class CollaborativeSessionCreate(CollaborativeSessionBase):
    pass


class CollaborativeSessionUpdate(BaseModel):
    session_name: Optional[str] = Field(None, min_length=2, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None
    max_users: Optional[int] = Field(None, ge=2, le=50)


class CollaborativeSessionInDB(CollaborativeSessionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int
    is_active: bool
    current_users: int
    created_at: datetime
    updated_at: datetime


class CollaborativeSession(CollaborativeSessionInDB):
    pass


class SessionParticipantBase(BaseModel):
    session_id: int
    user_id: int


class SessionParticipantInDB(SessionParticipantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    joined_at: datetime
    last_active: datetime
    is_online: bool


class SessionParticipant(SessionParticipantInDB):
    pass


class JoinSessionRequest(BaseModel):
    session_id: int


class SessionUserInfo(BaseModel):
    user_id: int
    username: str
    role: str
    is_online: bool
    joined_at: datetime
