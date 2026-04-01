import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import get_settings
from app.core.logging_config import setup_logging, get_logger
from app.core.exceptions import BaseAppException, handle_exception
from app.db.database import init_db, check_db_connection
from app.background_tasks import scheduler
from app.api import auth, upload, jobs

# 设置日志
setup_logging()
logger = get_logger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=" * 50)
    logger.info("点云处理服务启动中...")
    logger.info("=" * 50)
    
    # 检查数据库连接
    if not check_db_connection():
        logger.error("数据库连接失败，请检查配置")
        raise Exception("数据库连接失败")
    
    # 初始化数据库表
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        raise
    
    # 确保上传目录存在
    os.makedirs(settings.upload_dir, exist_ok=True)
    os.makedirs(settings.processed_dir, exist_ok=True)
    os.makedirs(settings.log_dir, exist_ok=True)
    logger.info(f"上传目录: {settings.upload_dir}")
    logger.info(f"处理结果目录: {settings.processed_dir}")
    
    # 启动后台任务调度器
    await scheduler.start()
    
    logger.info("点云处理服务启动完成")
    
    yield
    
    # 关闭时执行
    logger.info("点云处理服务关闭中...")
    await scheduler.stop()
    logger.info("点云处理服务已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="点云处理服务 API",
    description="支持点云数据上传、处理和管理的 RESTful API 服务",
    version="1.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该配置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(BaseAppException)
async def base_app_exception_handler(request: Request, exc: BaseAppException):
    """处理应用自定义异常"""
    logger.error(f"应用异常: {exc.message}, 路径: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证异常"""
    logger.warning(f"请求验证失败: {request.url.path}, 错误: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": 422,
                "message": "请求参数验证失败",
                "details": exc.errors()
            }
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """处理所有未捕获的异常"""
    logger.error(f"未处理的异常: {str(exc)}, 路径: {request.url.path}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": 500,
                "message": "服务器内部错误",
                "details": str(exc) if settings.log_level == "DEBUG" else None
            }
        }
    )


# 注册路由
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(jobs.router)


@app.get("/")
async def root():
    """根路径 - API 信息"""
    return {
        "success": True,
        "data": {
            "name": "点云处理服务 API",
            "version": "1.0.0",
            "description": "支持点云数据上传、处理和管理的 RESTful API 服务",
            "docs": "/docs",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    db_status = check_db_connection()
    
    status = "healthy" if db_status else "unhealthy"
    status_code = 200 if db_status else 503
    
    return JSONResponse(
        status_code=status_code,
        content={
            "success": db_status,
            "data": {
                "status": status,
                "database": "connected" if db_status else "disconnected",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat()
            }
        }
    )


@app.get("/api/v1/info")
async def api_info():
    """API 详细信息"""
    return {
        "success": True,
        "data": {
            "name": "点云处理服务 API",
            "version": "1.0.0",
            "features": [
                "点云文件上传（支持 .las, .laz, .ply, .pcd, .xyz, .pts）",
                "点云处理（滤波、分割、降采样、配准）",
                "异步处理任务",
                "JWT 认证",
                "大文件上传支持（最大 50MB）"
            ],
            "supported_formats": [".las", ".laz", ".ply", ".pcd", ".xyz", ".pts"],
            "processing_types": ["filter", "segment", "downsample", "register"],
            "max_file_size": settings.max_file_size,
            "upload_timeout": settings.upload_timeout
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )
