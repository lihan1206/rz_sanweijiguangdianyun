from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    decode_token, get_current_user_id
)
from app.core.exceptions import AuthenticationError, handle_exception
from app.db.database import get_db
from app.db.models import User, UserRole

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBearer()


# 请求模型
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    created_at: Optional[str]


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """用户注册"""
    try:
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(
            User.username == user_data.username
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在"
            )
        
        # 检查邮箱是否已存在
        existing_email = db.query(User).filter(
            User.email == user_data.email
        ).first()
        
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被注册"
            )
        
        # 创建新用户
        hashed_password = get_password_hash(user_data.password)
        
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"新用户注册成功: {new_user.username}")
        
        return {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role.value,
            "created_at": new_user.created_at.isoformat() if new_user.created_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"用户注册失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    try:
        # 查找用户
        user = db.query(User).filter(
            User.username == login_data.username
        ).first()
        
        if not user:
            raise AuthenticationError("用户名或密码错误")
        
        # 验证密码
        if not verify_password(login_data.password, user.hashed_password):
            raise AuthenticationError("用户名或密码错误")
        
        # 检查用户是否激活
        if not user.is_active:
            raise AuthenticationError("账户已被禁用")
        
        # 更新最后登录时间
        user.last_login = datetime.utcnow()
        db.commit()
        
        # 创建访问令牌
        settings = get_settings()
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role.value},
            expires_delta=access_token_expires
        )
        
        logger.info(f"用户登录成功: {user.username}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60
        }
        
    except AuthenticationError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"用户登录失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取当前用户信息"""
    try:
        user = db.query(User).filter(User.id == current_user_id).first()
        
        if not user:
            raise AuthenticationError("用户不存在")
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        
    except AuthenticationError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户信息失败: {str(e)}"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """刷新访问令牌"""
    try:
        token = credentials.credentials
        payload = decode_token(token)
        
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("无效的令牌")
        
        # 验证用户是否存在
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user or not user.is_active:
            raise AuthenticationError("用户不存在或已被禁用")
        
        # 创建新令牌
        settings = get_settings()
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        new_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role.value},
            expires_delta=access_token_expires
        )
        
        logger.info(f"令牌刷新成功: {user.username}")
        
        return {
            "access_token": new_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60
        }
        
    except AuthenticationError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"刷新令牌失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刷新令牌失败: {str(e)}"
        )


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """修改密码"""
    try:
        user = db.query(User).filter(User.id == current_user_id).first()
        
        if not user:
            raise AuthenticationError("用户不存在")
        
        # 验证旧密码
        if not verify_password(old_password, user.hashed_password):
            raise AuthenticationError("旧密码错误")
        
        # 更新密码
        user.hashed_password = get_password_hash(new_password)
        db.commit()
        
        logger.info(f"密码修改成功: {user.username}")
        
        return {
            "success": True,
            "message": "密码修改成功"
        }
        
    except AuthenticationError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"修改密码失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修改密码失败: {str(e)}"
        )
