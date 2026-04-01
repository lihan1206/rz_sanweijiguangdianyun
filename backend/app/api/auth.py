import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User, UserRole
from app.services.audit import write_audit_log

router = APIRouter(prefix="/auth", tags=["认证"])
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: EmailStr | None = None
    role: str = "viewer"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    logger.info("用户登录请求: %s", payload.username)

    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        logger.warning("登录失败: 用户不存在 - %s", payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.password_hash):
        logger.warning("登录失败: 密码错误 - %s", payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning("登录失败: 账号已禁用 - %s", payload.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    from app.core.config import get_settings
    settings = get_settings()
    token = create_access_token(subject=user.username)

    write_audit_log(
        db,
        action="用户登录",
        target_type="user",
        target_id=str(user.id),
        user_id=user.id,
        detail={"username": user.username},
    )
    db.commit()

    logger.info("用户登录成功: %s (角色: %s)", user.username, user.role.value)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role.value,
        is_active=current_user.is_active,
    )


@router.post("/register", response_model=UserResponse)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    try:
        role = UserRole(payload.role)
    except ValueError:
        role = UserRole.VIEWER

    user = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        action="用户注册",
        target_type="user",
        target_id=str(user.id),
        user_id=user.id,
        detail={"username": user.username, "role": role.value},
    )
    db.commit()

    logger.info("用户注册成功: %s (角色: %s)", user.username, role.value)

    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role.value,
        is_active=user.is_active,
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )

    current_user.password_hash = get_password_hash(payload.new_password)

    write_audit_log(
        db,
        action="修改密码",
        target_type="user",
        target_id=str(current_user.id),
        user_id=current_user.id,
        detail={"username": current_user.username},
    )
    db.commit()

    logger.info("用户修改密码: %s", current_user.username)

    return {"message": "密码修改成功"}


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    write_audit_log(
        db,
        action="用户登出",
        target_type="user",
        target_id=str(current_user.id),
        user_id=current_user.id,
        detail={"username": current_user.username},
    )
    db.commit()

    logger.info("用户登出: %s", current_user.username)

    return {"message": "登出成功"}


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    from app.core.config import get_settings
    settings = get_settings()
    token = create_access_token(subject=current_user.username)

    logger.info("Token刷新: %s", current_user.username)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )
