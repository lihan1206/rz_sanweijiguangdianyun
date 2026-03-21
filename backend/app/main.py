import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.models import audit_log, collaboration, pointcloud, task, user  # noqa: F401
from app.services.seed import seed_data

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="三维激光点云数据处理与可视化系统 - 支持多用户协同处理",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

register_exception_handlers(app)


@app.get("/health", tags=["系统"])
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_data(db, settings.upload_dir)
    finally:
        db.close()
    logger.info("服务启动完成")


app.include_router(api_router, prefix=settings.api_v1_prefix)
