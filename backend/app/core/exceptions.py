from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    FILE_FORMAT_UNSUPPORTED = "FILE_FORMAT_UNSUPPORTED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_CORRUPTED = "FILE_CORRUPTED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_PARSE_ERROR = "FILE_PARSE_ERROR"
    FILE_WRITE_ERROR = "FILE_WRITE_ERROR"

    PROCESSING_TIMEOUT = "PROCESSING_TIMEOUT"
    PROCESSING_MEMORY_ERROR = "PROCESSING_MEMORY_ERROR"
    PROCESSING_INVALID_PARAMS = "PROCESSING_INVALID_PARAMS"
    PROCESSING_ALGORITHM_ERROR = "PROCESSING_ALGORITHM_ERROR"
    PROCESSING_TASK_NOT_FOUND = "PROCESSING_TASK_NOT_FOUND"
    PROCESSING_SOURCE_NOT_FOUND = "PROCESSING_SOURCE_NOT_FOUND"

    SCENE_NOT_FOUND = "SCENE_NOT_FOUND"
    SCENE_INACTIVE = "SCENE_INACTIVE"
    SCENE_FULL = "SCENE_FULL"
    SCENE_SESSION_NOT_FOUND = "SCENE_SESSION_NOT_FOUND"
    SCENE_SESSION_EXPIRED = "SCENE_SESSION_EXPIRED"

    POINTCLOUD_NOT_FOUND = "POINTCLOUD_NOT_FOUND"
    POINTCLOUD_ALREADY_EXISTS = "POINTCLOUD_ALREADY_EXISTS"
    POINTCLOUD_EMPTY = "POINTCLOUD_EMPTY"

    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_UNAUTHORIZED = "USER_UNAUTHORIZED"
    USER_PERMISSION_DENIED = "USER_PERMISSION_DENIED"

    WEBSOCKET_INVALID_MESSAGE = "WEBSOCKET_INVALID_MESSAGE"
    WEBSOCKET_CONNECTION_ERROR = "WEBSOCKET_CONNECTION_ERROR"

    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    DATABASE_CONSTRAINT_ERROR = "DATABASE_CONSTRAINT_ERROR"

    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


class AppException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class FileException(AppException):
    pass


class ProcessingException(AppException):
    pass


class SceneException(AppException):
    pass


class PointCloudException(AppException):
    pass


class WebSocketException(AppException):
    pass


class DatabaseException(AppException):
    pass


def raise_file_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    status_map = {
        ErrorCode.FILE_FORMAT_UNSUPPORTED: 400,
        ErrorCode.FILE_TOO_LARGE: 413,
        ErrorCode.FILE_CORRUPTED: 422,
        ErrorCode.FILE_NOT_FOUND: 404,
        ErrorCode.FILE_PARSE_ERROR: 422,
        ErrorCode.FILE_WRITE_ERROR: 500,
    }
    raise FileException(
        code=code,
        message=message,
        status_code=status_map.get(code, 400),
        details=details,
    )


def raise_processing_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    status_map = {
        ErrorCode.PROCESSING_TIMEOUT: 408,
        ErrorCode.PROCESSING_MEMORY_ERROR: 503,
        ErrorCode.PROCESSING_INVALID_PARAMS: 400,
        ErrorCode.PROCESSING_ALGORITHM_ERROR: 500,
        ErrorCode.PROCESSING_TASK_NOT_FOUND: 404,
        ErrorCode.PROCESSING_SOURCE_NOT_FOUND: 404,
    }
    raise ProcessingException(
        code=code,
        message=message,
        status_code=status_map.get(code, 500),
        details=details,
    )


def raise_scene_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    status_map = {
        ErrorCode.SCENE_NOT_FOUND: 404,
        ErrorCode.SCENE_INACTIVE: 400,
        ErrorCode.SCENE_FULL: 400,
        ErrorCode.SCENE_SESSION_NOT_FOUND: 404,
        ErrorCode.SCENE_SESSION_EXPIRED: 401,
    }
    raise SceneException(
        code=code,
        message=message,
        status_code=status_map.get(code, 400),
        details=details,
    )


def raise_pointcloud_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    status_map = {
        ErrorCode.POINTCLOUD_NOT_FOUND: 404,
        ErrorCode.POINTCLOUD_ALREADY_EXISTS: 409,
        ErrorCode.POINTCLOUD_EMPTY: 422,
    }
    raise PointCloudException(
        code=code,
        message=message,
        status_code=status_map.get(code, 400),
        details=details,
    )


def raise_websocket_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    raise WebSocketException(
        code=code,
        message=message,
        status_code=400,
        details=details,
    )


def raise_database_error(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    status_map = {
        ErrorCode.DATABASE_ERROR: 500,
        ErrorCode.DATABASE_CONNECTION_ERROR: 503,
        ErrorCode.DATABASE_CONSTRAINT_ERROR: 409,
    }
    raise DatabaseException(
        code=code,
        message=message,
        status_code=status_map.get(code, 500),
        details=details,
    )
