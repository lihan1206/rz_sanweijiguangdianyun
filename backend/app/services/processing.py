from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus
from app.services.audit import write_audit_log
from app.utils.pointcloud_io import extract_metadata, load_points, run_processing, write_points

logger = logging.getLogger(__name__)


def execute_task(task_id: int, upload_dir: str) -> None:
    db: Session = SessionLocal()
    try:
        task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        if not task:
            logger.error("任务不存在: %s", task_id)
            return

        source = db.query(PointCloud).filter(PointCloud.id == task.pointcloud_id).first()
        if not source:
            task.status = TaskStatus.FAILED
            task.error_message = "源点云不存在"
            task.finished_at = datetime.utcnow()
            db.commit()
            return

        task.status = TaskStatus.RUNNING
        db.commit()

        points = load_points(source.storage_path, source.file_format)
        processed = run_processing(points, task.task_type.value, task.parameters or {})

        result_name = f"{Path(source.original_filename).stem}_{task.task_type.value}_{uuid.uuid4().hex[:8]}"
        output_filename = f"{result_name}.{task.output_format}"
        output_path = str(Path(upload_dir) / output_filename)
        write_points(processed, output_path, task.output_format)

        points_count, bbox = extract_metadata(output_path, task.output_format)

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
        task.finished_at = datetime.utcnow()

        write_audit_log(
            db,
            action="点云处理完成",
            target_type="processing_task",
            target_id=str(task.id),
            user_id=task.created_by,
            detail={"result_pointcloud_id": new_pc.id, "task_type": task.task_type.value},
        )

        db.commit()
        logger.info("任务执行成功: %s", task_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("任务执行失败: %s", task_id)
        task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(exc)
            task.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
