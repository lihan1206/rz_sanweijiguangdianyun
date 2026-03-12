from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.schemas.audit import AuditLogItem

router = APIRouter(prefix="/audit-logs", tags=["审计日志"])


@router.get("", response_model=list[AuditLogItem])
def list_logs(
    _: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> list[AuditLogItem]:
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return [AuditLogItem.model_validate(log) for log in logs]
