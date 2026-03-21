from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings
import redis
import json

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Bearer
security = HTTPBearer()

# Redis client for token blacklist
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """创建刷新令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """解码令牌"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def blacklist_token(token: str, exp: datetime) -> None:
    """将令牌加入黑名单"""
    ttl = int((exp - datetime.utcnow()).total_seconds())
    if ttl > 0:
        redis_client.setex(f"blacklist:{token}", ttl, "1")


def is_token_blacklisted(token: str) -> bool:
    """检查令牌是否在黑名单中"""
    return redis_client.exists(f"blacklist:{token}") == 1


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """获取当前用户ID（依赖函数）"""
    token = credentials.credentials
    
    # 检查黑名单
    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: int = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 检查token类型
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return int(user_id)


async def get_current_user_id_ws(token: str) -> Optional[int]:
    """WebSocket使用的用户认证"""
    if is_token_blacklisted(token):
        return None
    
    payload = decode_token(token)
    if payload is None:
        return None
    
    user_id = payload.get("sub")
    token_type = payload.get("type")
    
    if user_id is None or token_type != "access":
        return None
    
    return int(user_id)


class RateLimiter:
    """请求频率限制器"""
    
    def __init__(self, key_prefix: str, max_requests: int, window_seconds: int):
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def is_allowed(self, identifier: str) -> bool:
        """检查是否允许请求"""
        key = f"{self.key_prefix}:{identifier}"
        current = redis_client.get(key)
        
        if current is None:
            redis_client.setex(key, self.window_seconds, 1)
            return True
        
        count = int(current)
        if count >= self.max_requests:
            return False
        
        redis_client.incr(key)
        return True
    
    def get_remaining(self, identifier: str) -> int:
        """获取剩余请求次数"""
        key = f"{self.key_prefix}:{identifier}"
        current = redis_client.get(key)
        if current is None:
            return self.max_requests
        return max(0, self.max_requests - int(current))
    
    def get_reset_time(self, identifier: str) -> int:
        """获取重置时间戳"""
        key = f"{self.key_prefix}:{identifier}"
        ttl = redis_client.ttl(key)
        if ttl < 0:
            return int(datetime.utcnow().timestamp()) + self.window_seconds
        return int(datetime.utcnow().timestamp()) + ttl


# 预定义的限流器
login_limiter = RateLimiter("login", 5, 300)  # 5次/5分钟
upload_limiter = RateLimiter("upload", 10, 60)  # 10次/分钟
task_limiter = RateLimiter("task", 20, 60)  # 20次/分钟
api_limiter = RateLimiter("api", 100, 60)  # 100次/分钟
