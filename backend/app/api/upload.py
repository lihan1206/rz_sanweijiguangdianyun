from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import FileException, PointCloudException, raise_file_error
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus, TaskType
from app.models.user import User, UserRole
from app.services.audit import write_audit_log
from app.services.background_tasks import process_point_cloud_background
from app.services.point_cloud_service import PointCloudService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["文件上传"])
settings = get_settings()
point_cloud_service = PointCloudService()

SUPPORTED_FORMATS = {"las", "laz", "ply", "xyz", "csv"}


class UploadResponse(BaseModel):
    id: int
    message: str
    file_size: int
    file_format: str
    points_count: int | None = None


class ProcessingRequest(BaseModel):
    pointcloud_id: int
    processing_type: str
    parameters: dict[str, Any] | None = None
    output_format: str = "ply"


class ProcessingResponse(BaseModel):
    task_id: int
    message: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: int
    status: str
    progress: int
    error_message: str | None = None
    result_pointcloud_id: int | None = None


def validate_file_format(filename: str | None) -> str:
    if not filename:
        raise_file_error(
            "FILE_FORMAT_UNSUPPORTED",
            "文件名不能为空",
        )
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_FORMATS:
        raise_file_error(
            "FILE_FORMAT_UNSUPPORTED",
            f"不支持的点云格式: {suffix}，支持的格式: {', '.join(SUPPORTED_FORMATS)}",
            {"supported_formats": list(SUPPORTED_FORMATS), "received_format": suffix},
        )
    return suffix


async def save_upload_file(
    upload_file: UploadFile,
    upload_dir: str,
    max_size: int,
) -> tuple[str, int, str]:
    file_format = validate_file_format(upload_file.filename)

    target_dir = Path(upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}.{file_format}"
    target_path = target_dir / safe_name

    size = 0
    chunk_size = settings.chunk_size

    try:
        with target_path.open("wb") as f:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size:
                    if target_path.exists():
                        target_path.unlink()
                    raise_file_error(
                        "FILE_TOO_LARGE",
                        f"文件大小超过限制: {size / 1024 / 1024:.2f}MB > {max_size / 1024 / 1024:.2f}MB",
                        {
                            "max_size_mb": max_size / 1024 / 1024,
                            "actual_size_mb": size / 1024 / 1024,
                        },
                    )
                f.write(chunk)
    except FileException:
        raise
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        raise_file_error(
            "FILE_WRITE_ERROR",
            f"文件保存失败: {str(e)}",
            {"filename": upload_file.filename, "error": str(e)},
        )

    if size == 0:
        if target_path.exists():
            target_path.unlink()
        raise_file_error(
            "FILE_EMPTY",
            "上传的文件为空",
            {"filename": upload_file.filename},
        )

    logger.info("文件上传成功: %s, 大小: %.2fMB", target_path, size / 1024 / 1024)
    return str(target_path), size, file_format


@router.post("", response_model=UploadResponse)
async def upload_pointcloud(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    group_name: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    capture_time: str | None = Form(default=None),
    sensor_model: str | None = Form(default=None),
    coordinate_system: str | None = Form(default=None),
    auto_process: str | None = Form(default=None),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> UploadResponse:
    logger.info(
        "用户 %s 开始上传文件: %s",
        current_user.username,
        file.filename,
    )

    storage_path, file_size, file_format = await save_upload_file(
        file,
        settings.upload_dir,
        settings.max_file_size_bytes,
    )

    points_count = None
    bounding_box = None

    try:
        metadata = point_cloud_service.extract_metadata(storage_path, file_format)
        points_count = metadata["points_count"]
        bounding_box = metadata["bounding_box"]
    except Exception as e:
        logger.warning("提取点云元数据失败: %s", str(e))

    parsed_capture_time = None
    if capture_time:
        try:
            parsed_capture_time = datetime.fromisoformat(capture_time.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("采集时间格式错误: %s", capture_time)

    parsed_tags = []
    if tags:
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

    record = PointCloud(
        name=name,
        original_filename=file.filename or "未知文件",
        storage_path=storage_path,
        file_format=file_format,
        file_size=file_size,
        points_count=points_count,
        capture_time=parsed_capture_time,
        sensor_model=sensor_model,
        coordinate_system=coordinate_system,
        bounding_box=bounding_box,
        group_name=group_name,
        tags=parsed_tags,
        created_by=current_user.id,
    )
    db.add(record)
    db.flush()

    write_audit_log(
        db,
        action="上传点云",
        target_type="pointcloud",
        target_id=str(record.id),
        user_id=current_user.id,
        detail={
            "name": name,
            "format": file_format,
            "size_mb": file_size / 1024 / 1024,
            "points_count": points_count,
        },
    )

    if auto_process:
        try:
            task = ProcessingTask(
                pointcloud_id=record.id,
                task_type=TaskType(auto_process),
                parameters={},
                status=TaskStatus.PENDING,
                created_by=current_user.id,
            )
            db.add(task)
            db.flush()

            background_tasks.add_task(
                process_point_cloud_background,
                task.id,
                auto_process,
                {},
            )

            write_audit_log(
                db,
                action="创建处理任务",
                target_type="processing_task",
                target_id=str(task.id),
                user_id=current_user.id,
                detail={"processing_type": auto_process},
            )
        except ValueError:
            logger.warning("无效的处理类型: %s", auto_process)

    db.commit()

    logger.info(
        "点云上传完成: ID=%d, 用户=%s, 文件=%s",
        record.id,
        current_user.username,
        file.filename,
    )

    return UploadResponse(
        id=record.id,
        message="上传成功",
        file_size=file_size,
        file_format=file_format,
        points_count=points_count,
    )


@router.post("/process", response_model=ProcessingResponse)
async def create_processing_task(
    request: ProcessingRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> ProcessingResponse:
    pointcloud = db.query(PointCloud).filter(PointCloud.id == request.pointcloud_id).first()
    if not pointcloud:
        raise HTTPException(status_code=404, detail="点云数据不存在")

    if pointcloud.is_deleted:
        raise HTTPException(status_code=400, detail="点云数据已被删除")

    try:
        task_type = TaskType(request.processing_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的处理类型: {request.processing_type}",
        )

    task = ProcessingTask(
        pointcloud_id=request.pointcloud_id,
        task_type=task_type,
        parameters=request.parameters or {},
        output_format=request.output_format,
        status=TaskStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(task)
    db.flush()

    write_audit_log(
        db,
        action="创建处理任务",
        target_type="processing_task",
        target_id=str(task.id),
        user_id=current_user.id,
        detail={
            "processing_type": request.processing_type,
            "pointcloud_id": request.pointcloud_id,
            "parameters": request.parameters,
        },
    )

    db.commit()

    background_tasks.add_task(
        process_point_cloud_background,
        task.id,
        request.processing_type,
        request.parameters,
    )

    logger.info(
        "处理任务已创建: task_id=%d, type=%s, pointcloud_id=%d, user=%s",
        task.id,
        request.processing_type,
        request.pointcloud_id,
        current_user.username,
    )

    return ProcessingResponse(
        task_id=task.id,
        message="处理任务已创建，正在后台执行",
        status=TaskStatus.PENDING.value,
    )


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskStatusResponse:
    task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status.value,
        progress=task.progress,
        error_message=task.error_message,
        result_pointcloud_id=task.result_pointcloud_id,
    )


@router.post("/chunk/init")
async def init_chunk_upload(
    filename: str = Form(...),
    total_size: int = Form(...),
    chunk_size: int = Form(...),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> dict:
    file_format = validate_file_format(filename)

    if total_size > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制: {total_size / 1024 / 1024:.2f}MB > {settings.max_file_size_mb}MB",
        )

    upload_id = uuid.uuid4().hex
    total_chunks = (total_size + chunk_size - 1) // chunk_size

    temp_dir = Path(settings.upload_dir) / "chunks" / upload_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "upload_id": upload_id,
        "filename": filename,
        "file_format": file_format,
        "total_size": total_size,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
        "uploaded_chunks": [],
        "created_by": current_user.id,
    }

    metadata_file = temp_dir / "metadata.txt"
    with open(metadata_file, "w") as f:
        f.write(f"filename={filename}\n")
        f.write(f"file_format={file_format}\n")
        f.write(f"total_size={total_size}\n")
        f.write(f"total_chunks={total_chunks}\n")
        f.write(f"created_by={current_user.id}\n")

    logger.info(
        "分片上传初始化: upload_id=%s, filename=%s, total_chunks=%d",
        upload_id,
        filename,
        total_chunks,
    )

    return {
        "upload_id": upload_id,
        "total_chunks": total_chunks,
        "chunk_size": chunk_size,
    }


@router.post("/chunk/{upload_id}/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
) -> dict:
    temp_dir = Path(settings.upload_dir) / "chunks" / upload_id
    if not temp_dir.exists():
        raise HTTPException(status_code=404, detail="上传会话不存在")

    chunk_file = temp_dir / f"chunk_{chunk_index}"
    chunk_data = await chunk.read()

    with open(chunk_file, "wb") as f:
        f.write(chunk_data)

    logger.debug("分片上传完成: upload_id=%s, chunk_index=%d", upload_id, chunk_index)

    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "size": len(chunk_data),
    }


@router.post("/chunk/complete/{upload_id}")
async def complete_chunk_upload(
    upload_id: str,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> UploadResponse:
    temp_dir = Path(settings.upload_dir) / "chunks" / upload_id
    if not temp_dir.exists():
        raise HTTPException(status_code=404, detail="上传会话不存在")

    metadata_file = temp_dir / "metadata.txt"
    if not metadata_file.exists():
        raise HTTPException(status_code=400, detail="上传元数据不存在")

    metadata = {}
    with open(metadata_file, "r") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                metadata[key] = value

    total_chunks = int(metadata.get("total_chunks", 0))
    file_format = metadata.get("file_format", "ply")
    filename = metadata.get("filename", "unknown")

    for i in range(total_chunks):
        chunk_file = temp_dir / f"chunk_{i}"
        if not chunk_file.exists():
            raise HTTPException(
                status_code=400,
                detail=f"分片 {i} 缺失",
            )

    safe_name = f"{uuid.uuid4().hex}.{file_format}"
    target_path = Path(settings.upload_dir) / safe_name

    total_size = 0
    with open(target_path, "wb") as outfile:
        for i in range(total_chunks):
            chunk_file = temp_dir / f"chunk_{i}"
            with open(chunk_file, "rb") as infile:
                data = infile.read()
                outfile.write(data)
                total_size += len(data)

    import shutil
    shutil.rmtree(temp_dir)

    points_count = None
    bounding_box = None

    try:
        meta = point_cloud_service.extract_metadata(str(target_path), file_format)
        points_count = meta["points_count"]
        bounding_box = meta["bounding_box"]
    except Exception as e:
        logger.warning("提取点云元数据失败: %s", str(e))

    record = PointCloud(
        name=name,
        original_filename=filename,
        storage_path=str(target_path),
        file_format=file_format,
        file_size=total_size,
        points_count=points_count,
        bounding_box=bounding_box,
        created_by=current_user.id,
    )
    db.add(record)
    db.flush()

    write_audit_log(
        db,
        action="分片上传完成",
        target_type="pointcloud",
        target_id=str(record.id),
        user_id=current_user.id,
        detail={
            "name": name,
            "format": file_format,
            "size_mb": total_size / 1024 / 1024,
            "points_count": points_count,
        },
    )

    db.commit()

    logger.info(
        "分片上传合并完成: ID=%d, 用户=%s, 文件=%s, 大小=%.2fMB",
        record.id,
        current_user.username,
        filename,
        total_size / 1024 / 1024,
    )

    return UploadResponse(
        id=record.id,
        message="上传成功",
        file_size=total_size,
        file_format=file_format,
        points_count=points_count,
    )
