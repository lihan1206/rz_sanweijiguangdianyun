from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Dict, Any

from app.core.database import get_db
from app.core.security import (
    verify_password, get_password_hash, create_access_token, 
    create_refresh_token, decode_token, blacklist_token, 
    get_current_user_id, security, login_limiter
)
from app.models.user import User
from app.utils.schemas import (
    UserCreate, UserLogin, TokenResponse, UserResponse, 
    ResponseBase, ErrorResponse
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # 检查邮箱是否已存在
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    # 创建新用户
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return ResponseBase(
        code=201,
        message="User registered successfully",
        data={
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "created_at": new_user.created_at.isoformat() if new_user.created_at else None
        }
    )


@router.post("/login", response_model=ResponseBase)
async def login(
    request: Request,
    login_data: UserLogin, 
    db: AsyncSession = Depends(get_db)
):
    """用户登录"""
    # 限流检查
    client_ip = request.client.host
    if not login_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later."
        )
    
    # 查找用户
    result = await db.execute(
        select(User).where(
            (User.username == login_data.username) | (User.email == login_data.username)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # 创建令牌
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return ResponseBase(
        code=200,
        message="Login successful",
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value if user.role else "user"
            }
        }
    )


@router.post("/refresh", response_model=ResponseBase)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """刷新访问令牌"""
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # 检查token类型
    token_type = payload.get("type")
    if token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    # 创建新的访问令牌
    new_access_token = create_access_token({"sub": user_id})
    
    return ResponseBase(
        code=200,
        data={
            "access_token": new_access_token,
            "token_type": "Bearer",
            "expires_in": 3600
        }
    )


@router.post("/logout", response_model=ResponseBase)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """用户登出"""
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload:
        exp = datetime.fromtimestamp(payload.get("exp", 0))
        # 将token加入黑名单
        blacklist_token(token, exp)
    
    return ResponseBase(
        code=200,
        message="Logout successful"
    )


@router.get("/me", response_model=ResponseBase)
async def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户信息"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return ResponseBase(
        code=200,
        data=user.to_dict()
    )
