import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.core.exceptions import (
    AppException,
    DatabaseException,
    ErrorCode,
    FileException,
    PointCloudException,
    ProcessingException,
    SceneException,
    WebSocketException,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "应用异常: %s - %s (路径: %s)",
            exc.code.value,
            exc.message,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(FileException)
    async def file_exception_handler(request: Request, exc: FileException) -> JSONResponse:
        logger.warning(
            "文件异常: %s - %s (路径: %s)",
            exc.code.value,
            exc.message,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(ProcessingException)
    async def processing_exception_handler(request: Request, exc: ProcessingException) -> JSONResponse:
        logger.error(
            "处理异常: %s - %s (路径: %s)",
            exc.code.value,
            exc.message,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(SceneException)
    async def scene_exception_handler(request: Request, exc: SceneException) -> JSONResponse:
        logger.warning(
            "场景异常: %s - %s (路径: %s)",
            exc.code.value,
            exc.message,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(PointCloudException)
    async def pointcloud_exception_handler(request: Request, exc: PointCloudException) -> JSONResponse:
        logger.warning(
            "点云异常: %s - %s (路径: %s)",
            exc.code.value,
            exc.message,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(WebSocketException)
    async def websocket_exception_handler(request: Request, exc: WebSocketException) -> JSONResponse:
        logger.warning(
            "WebSocket异常: %s - %s",
            exc.code.value,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(DatabaseException)
    async def database_exception_handler(request: Request, exc: DatabaseException) -> JSONResponse:
        logger.error(
            "数据库异常: %s - %s (路径: %s)",
            exc.code.value,
            exc.message,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })

        logger.warning(
            "请求验证失败 (路径: %s): %s",
            request.url.path,
            errors,
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": ErrorCode.PROCESSING_INVALID_PARAMS.value,
                "message": "请求参数验证失败",
                "details": {"errors": errors},
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.error(
            "数据库完整性错误 (路径: %s): %s",
            request.url.path,
            str(exc),
        )

        error_msg = "数据操作冲突"
        if "Duplicate entry" in str(exc):
            error_msg = "数据已存在，无法重复创建"
        elif "foreign key constraint" in str(exc).lower():
            error_msg = "关联数据不存在"

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": ErrorCode.DATABASE_CONSTRAINT_ERROR.value,
                "message": error_msg,
                "details": {},
            },
        )

    @app.exception_handler(OperationalError)
    async def operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        logger.error(
            "数据库连接错误 (路径: %s): %s",
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "code": ErrorCode.DATABASE_CONNECTION_ERROR.value,
                "message": "数据库服务暂时不可用，请稍后重试",
                "details": {},
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "数据库错误 (路径: %s): %s",
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": ErrorCode.DATABASE_ERROR.value,
                "message": "数据库操作失败",
                "details": {},
            },
        )

    @app.exception_handler(MemoryError)
    async def memory_error_handler(request: Request, exc: MemoryError) -> JSONResponse:
        logger.error(
            "内存不足 (路径: %s)",
            request.url.path,
        )

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "code": ErrorCode.PROCESSING_MEMORY_ERROR.value,
                "message": "服务器内存不足，请尝试处理较小的文件",
                "details": {},
            },
        )

    @app.exception_handler(TimeoutError)
    async def timeout_error_handler(request: Request, exc: TimeoutError) -> JSONResponse:
        logger.error(
            "请求超时 (路径: %s)",
            request.url.path,
        )

        return JSONResponse(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            content={
                "code": ErrorCode.PROCESSING_TIMEOUT.value,
                "message": "请求处理超时，请稍后重试",
                "details": {},
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "未处理的异常 (路径: %s): %s",
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "服务器内部错误，请稍后重试",
                "details": {},
            },
        )
