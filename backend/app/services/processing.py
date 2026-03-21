from __future__ import annotations

import json
import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import (
    ErrorCode,
    ProcessingException,
    raise_processing_error,
)
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus, TaskType
from app.services.audit import write_audit_log
from app.utils.advanced_processing import run_advanced_processing
from app.utils.pointcloud_io import (
    FileException,
    PointCloudException,
    extract_metadata,
    load_points,
    run_processing,
    write_points,
)

logger = logging.getLogger(__name__)

websocket_manager = None


def set_websocket_manager(manager) -> None:
    global websocket_manager
    websocket_manager = manager


async def broadcast_task_progress(scene_id: int, task_id: int, progress: int, status: str, message: str = "") -> None:
    if websocket_manager is None:
        return
    try:
        await websocket_manager.broadcast_to_scene(
            scene_id,
            {
                "event_type": "task_progress",
                "task_id": task_id,
                "progress": progress,
                "status": status,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception:
        logger.exception("广播任务进度失败")


def update_task_status(
    db: Session,
    task: ProcessingTask,
    status: TaskStatus,
    progress: int = 0,
    error_message: str | None = None,
) -> None:
    try:
        task.status = status
        task.progress = progress
        if error_message:
            task.error_message = error_message
        if status in (TaskStatus.SUCCESS, TaskStatus.FAILED):
            task.finished_at = datetime.utcnow()
        db.commit()
    except SQLAlchemyError:
        logger.exception("更新任务状态失败")
        db.rollback()


def execute_task(task_id: int, upload_dir: str) -> None:
    db: Session = SessionLocal()
    task: ProcessingTask | None = None

    try:
        task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        if not task:
            logger.error("任务不存在: %s", task_id)
            return

        source = db.query(PointCloud).filter(PointCloud.id == task.pointcloud_id).first()
        if not source:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message="源点云不存在",
            )
            return

        if source.is_deleted:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message="源点云已被删除",
            )
            return

        update_task_status(db, task, TaskStatus.RUNNING, progress=5)

        try:
            points = load_points(source.storage_path, source.file_format)
        except (FileException, PointCloudException) as e:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"加载点云失败: {e.message}",
            )
            return
        except Exception as e:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"加载点云失败: {str(e)}",
            )
            return

        if points.size == 0:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message="点云数据为空",
            )
            return

        update_task_status(db, task, TaskStatus.RUNNING, progress=20)

        advanced_tasks = {
            TaskType.VOXEL_GRID_FILTER,
            TaskType.STATISTICAL_OUTLIER_REMOVAL,
            TaskType.RANSAC_PLANE_SEGMENTATION,
            TaskType.ICP_REGISTRATION,
        }

        processed = None
        result_info = {}

        try:
            if task.task_type in advanced_tasks:
                target_points = None
                if task.task_type == TaskType.ICP_REGISTRATION:
                    target_pc_id = task.parameters.get("target_pointcloud_id") if task.parameters else None
                    if not target_pc_id:
                        raise_processing_error(
                            ErrorCode.PROCESSING_INVALID_PARAMS,
                            "ICP配准需要指定目标点云ID",
                        )
                    target_pc = db.query(PointCloud).filter(PointCloud.id == target_pc_id).first()
                    if not target_pc:
                        raise_processing_error(
                            ErrorCode.PROCESSING_SOURCE_NOT_FOUND,
                            f"目标点云不存在: {target_pc_id}",
                        )
                    if target_pc.is_deleted:
                        raise_processing_error(
                            ErrorCode.PROCESSING_INVALID_PARAMS,
                            "目标点云已被删除",
                        )
                    try:
                        target_points = load_points(target_pc.storage_path, target_pc.file_format)
                    except Exception as e:
                        raise_processing_error(
                            ErrorCode.FILE_PARSE_ERROR,
                            f"加载目标点云失败: {str(e)}",
                        )

                processed, result_info = run_advanced_processing(
                    points,
                    task.task_type.value,
                    task.parameters or {},
                    target_points=target_points,
                )
            else:
                processed = run_processing(points, task.task_type.value, task.parameters or {})
                result_info = {}

            update_task_status(db, task, TaskStatus.RUNNING, progress=70)

        except ProcessingException as e:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"处理失败: {e.message}",
            )
            return
        except MemoryError:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message="内存不足，无法完成处理，请尝试处理较小的点云或增加服务器内存",
            )
            return
        except Exception as e:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"处理失败: {str(e)}",
            )
            logger.exception("任务处理异常")
            return

        if processed is None or processed.size == 0:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message="处理结果为空",
            )
            return

        result_name = f"{Path(source.original_filename).stem}_{task.task_type.value}_{uuid.uuid4().hex[:8]}"
        output_filename = f"{result_name}.{task.output_format}"
        output_path = str(Path(upload_dir) / output_filename)

        try:
            write_points(processed, output_path, task.output_format)
        except (FileException, PointCloudException) as e:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"保存结果失败: {e.message}",
            )
            return
        except Exception as e:
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"保存结果失败: {str(e)}",
            )
            return

        update_task_status(db, task, TaskStatus.RUNNING, progress=90)

        try:
            points_count, bbox = extract_metadata(output_path, task.output_format)
        except Exception:
            points_count = len(processed)
            bbox = None

        try:
            new_pc = PointCloud(
                name=f"{source.name}-处理结果",
                original_filename=output_filename,
                storage_path=output_path,
                file_format=task.output_format,
                file_size=Path(output_path).stat().st_size,
                points_count=points_count,
                capture_time=source.capture_time,
                sensor_model=source.sensor_model,
                coordinate_system=source.coordinate_system,
                bounding_box=bbox,
                group_name=source.group_name,
                tags=(source.tags or []) + ["处理结果"],
                version=source.version + 1,
                created_by=task.created_by,
            )
            db.add(new_pc)
            db.flush()

            task.result_pointcloud_id = new_pc.id
            task.status = TaskStatus.SUCCESS
            task.progress = 100
            task.finished_at = datetime.utcnow()

            write_audit_log(
                db,
                action="点云处理完成",
                target_type="processing_task",
                target_id=str(task.id),
                user_id=task.created_by,
                detail={
                    "result_pointcloud_id": new_pc.id,
                    "task_type": task.task_type.value,
                    "result_info": result_info,
                },
            )

            db.commit()
            logger.info("任务执行成功: %s", task_id)

        except SQLAlchemyError as e:
            logger.exception("保存处理结果失败")
            db.rollback()
            update_task_status(
                db,
                task,
                TaskStatus.FAILED,
                error_message=f"保存处理结果失败: {str(e)}",
            )
            return

    except Exception:
        logger.exception("任务执行发生未预期错误: %s", task_id)
        if task:
            try:
                update_task_status(
                    db,
                    task,
                    TaskStatus.FAILED,
                    error_message="任务执行发生未预期错误",
                )
            except Exception:
                pass

    finally:
        try:
            db.close()
        except Exception:
            pass


def execute_task_async(task_id: int, upload_dir: str) -> None:
    import threading
    thread = threading.Thread(target=execute_task, args=(task_id, upload_dir))
    thread.daemon = True
    thread.start()
