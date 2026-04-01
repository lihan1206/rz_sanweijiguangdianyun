from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.core.celery_app import celery
from app.core.database import SessionLocal
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus
from app.services.audit import write_audit_log
from app.utils.pointcloud_io import extract_metadata, load_points, run_processing, write_points, write_mesh_data
from app.utils.pointcloud_processing import poisson_surface_reconstruction, marching_cubes_reconstruction

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="process_pointcloud")
def process_pointcloud(self, task_id: int, upload_dir: str):
    """Celery 任务：处理点云数据"""
    db = SessionLocal()
    celery_task_id = self.request.id
    
    try:
        task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        if not task:
            logger.error("任务不存在: %s", task_id)
            return {"status": "failed", "error": "任务不存在"}

        source = db.query(PointCloud).filter(PointCloud.id == task.pointcloud_id).first()
        if not source:
            task.status = TaskStatus.FAILED
            task.error_message = "源点云不存在"
            task.finished_at = datetime.utcnow()
            db.commit()
            return {"status": "failed", "error": "源点云不存在"}

        task.status = TaskStatus.RUNNING
        db.commit()

        # 检查是否是网格化任务
        is_mesh_task = task.task_type.value in ["poisson_reconstruction", "meshing"]
        
        if is_mesh_task:
            # 网格化任务
            points = load_points(source.storage_path, source.file_format)
            
            if task.task_type.value == "poisson_reconstruction":
                depth = int((task.parameters or {}).get("depth", 8))
                min_density = float((task.parameters or {}).get("min_density", 0.01))
                vertices, faces = poisson_surface_reconstruction(points, depth, min_density)
            else:  # meshing
                voxel_size = float((task.parameters or {}).get("voxel_size", 0.1))
                vertices, faces = marching_cubes_reconstruction(points, voxel_size)
            
            # 生成结果文件
            result_name = f"{Path(source.original_filename).stem}_{task.task_type.value}_{uuid.uuid4().hex[:8]}"
            output_format = task.output_format if task.output_format in ["ply", "obj", "stl"] else "ply"
            output_filename = f"{result_name}.{output_format}"
            output_path = str(Path(upload_dir) / output_filename)
            
            write_mesh_data(vertices, faces, output_path, output_format)
            
            points_count = len(vertices)
            if points_count > 0:
                bbox = {
                    "x": [float(vertices[:, 0].min()), float(vertices[:, 0].max())],
                    "y": [float(vertices[:, 1].min()), float(vertices[:, 1].max())],
                    "z": [float(vertices[:, 2].min()), float(vertices[:, 2].max())],
                }
            else:
                bbox = {"x": [0, 0], "y": [0, 0], "z": [0, 0]}
        else:
            # 普通点云处理任务
            points = load_points(source.storage_path, source.file_format)
            processed = run_processing(points, task.task_type.value, task.parameters or {})

            result_name = f"{Path(source.original_filename).stem}_{task.task_type.value}_{uuid.uuid4().hex[:8]}"
            output_filename = f"{result_name}.{task.output_format}"
            output_path = str(Path(upload_dir) / output_filename)
            write_points(processed, output_path, task.output_format)

            points_count, bbox = extract_metadata(output_path, task.output_format)

        # 创建新的点云记录
        new_pc = PointCloud(
            name=f"{source.name}-处理结果",
            original_filename=output_filename,
            storage_path=output_path,
            file_format=output_format if is_mesh_task else task.output_format,
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
        return {"status": "success", "task_id": task_id, "result_id": new_pc.id}

    except Exception as exc:
        logger.exception("任务执行失败: %s", task_id)
        task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(exc)
            task.finished_at = datetime.utcnow()
            db.commit()
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


@celery.task(name="check_task_timeout")
def check_task_timeout(timeout_seconds: int = 600):
    """检查超时任务"""
    from datetime import timedelta
    
    db = SessionLocal()
    try:
        cutoff_time = datetime.utcnow() - timedelta(seconds=timeout_seconds)
        running_tasks = db.query(ProcessingTask).filter(
            ProcessingTask.status == TaskStatus.RUNNING,
            ProcessingTask.updated_at < cutoff_time
        ).all()
        
        for task in running_tasks:
            logger.warning("任务超时，强制终止: %s", task.id)
            task.status = TaskStatus.FAILED
            task.error_message = f"任务执行超时（超过 {timeout_seconds} 秒）"
            task.finished_at = datetime.utcnow()
            
            write_audit_log(
                db,
                action="任务超时终止",
                target_type="processing_task",
                target_id=str(task.id),
                user_id=task.created_by,
            )
        
        db.commit()
    finally:
        db.close()
