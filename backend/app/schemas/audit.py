from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: int | None
    action: str
    target_type: str
    target_id: str
    detail: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
