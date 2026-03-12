from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.schemas.user import UserCreateRequest, UserListItem

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=list[UserListItem])
def list_users(
    _: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> list[UserListItem]:
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserListItem.model_validate(item) for item in users]


@router.post("", response_model=UserListItem)
def create_user(
    payload: UserCreateRequest,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> UserListItem:
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserListItem.model_validate(user)
