from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import time
import uuid

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api import auth, pointclouds, tasks, scenes, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    await init_db()
    print("Database initialized")
    
    yield
    
    # 关闭时清理
    await close_db()
    print("Database connection closed")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-user collaborative point cloud processing and visualization system",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求ID中间件
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求添加唯一ID"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": 500,
            "message": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "details": {"error": str(exc)} if settings.DEBUG else None,
            "timestamp": time.time(),
            "request_id": request_id
        }
    )


# 注册路由
app.include_router(auth.router, prefix="/api/v1")
app.include_router(pointclouds.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(scenes.router, prefix="/api/v1")
app.include_router(websocket.router)

# 静态文件服务（用于上传和处理的文件）
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/processed", StaticFiles(directory=settings.PROCESSED_DIR), name="processed")


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": "/api/v1"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": time.time()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else 4
    )
