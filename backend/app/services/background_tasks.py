from __future__ import annotations

import asyncio
import logging
import signal
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator

import numpy as np

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.exceptions import ProcessingException, raise_processing_error
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus, TaskType
from app.services.point_cloud_service import PointCloudService

logger = logging.getLogger(__name__)
settings = get_settings()

_task_executor = ThreadPoolExecutor(max_workers=4)


class TimeoutError(Exception):
    pass


class TaskCancelledError(Exception):
    pass


@contextmanager
def timeout_context(seconds: int) -> Generator[None, None, None]:
    def timeout_handler(signum, frame):
        raise TimeoutError(f"处理超时: 超过 {seconds} 秒")

    original_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)


class BackgroundTaskManager:
    def __init__(self):
        self.service = PointCloudService()
        self.running_tasks: dict[int, asyncio.Task] = {}
        self.timeout = settings.celery_task_timeout
        self.soft_timeout = settings.celery_task_soft_timeout

    async def submit_processing_task(
        self,
        task_id: int,
        processing_type: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._execute_with_timeout(task_id, processing_type, parameters or {})
        )
        self.running_tasks[task_id] = task

        try:
            await task
        except asyncio.CancelledError:
            logger.warning("任务被取消: %d", task_id)
            await self._update_task_status(task_id, TaskStatus.FAILED, error_message="任务被取消")
        except TimeoutError:
            logger.error("任务超时: %d", task_id)
            await self._update_task_status(task_id, TaskStatus.FAILED, error_message=f"处理超时（超过 {self.timeout} 秒）")
        except Exception as e:
            logger.exception("任务执行异常: %d - %s", task_id, str(e))
            await self._update_task_status(task_id, TaskStatus.FAILED, error_message=str(e))
        finally:
            self.running_tasks.pop(task_id, None)

    async def _execute_with_timeout(
        self,
        task_id: int,
        processing_type: str,
        parameters: dict[str, Any],
    ) -> None:
        loop = asyncio.get_event_loop()

        try:
            await asyncio.wait_for(
                loop.run_in_executor(
                    _task_executor,
                    self._execute_task_sync,
                    task_id,
                    processing_type,
                    parameters,
                ),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"处理超时: 超过 {self.timeout} 秒")

    def _execute_task_sync(
        self,
        task_id: int,
        processing_type: str,
        parameters: dict[str, Any],
    ) -> None:
        db = SessionLocal()
        task: ProcessingTask | None = None

        try:
            task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
            if not task:
                logger.error("任务不存在: %s", task_id)
                return

            self._update_task_status_sync(db, task, TaskStatus.RUNNING, progress=5)

            source = db.query(PointCloud).filter(PointCloud.id == task.pointcloud_id).first()
            if not source:
                self._update_task_status_sync(db, task, TaskStatus.FAILED, error_message="源点云不存在")
                return

            if source.is_deleted:
                self._update_task_status_sync(db, task, TaskStatus.FAILED, error_message="源点云已被删除")
                return

            self._update_task_status_sync(db, task, TaskStatus.RUNNING, progress=10)

            points = self.service.load_point_cloud(source.storage_path, source.file_format)

            if len(points) == 0:
                self._update_task_status_sync(db, task, TaskStatus.FAILED, error_message="点云数据为空")
                return

            self._update_task_status_sync(db, task, TaskStatus.RUNNING, progress=30)

            result_points, result_info = self._process_points(points, processing_type, parameters)

            self._update_task_status_sync(db, task, TaskStatus.RUNNING, progress=70)

            if result_points is None or len(result_points) == 0:
                self._update_task_status_sync(db, task, TaskStatus.FAILED, error_message="处理结果为空")
                return

            output_format = parameters.get("output_format", "ply")
            result_name = f"{Path(source.original_filename).stem}_{processing_type}_{uuid.uuid4().hex[:8]}"
            output_filename = f"{result_name}.{output_format}"
            output_path = str(Path(settings.upload_dir) / output_filename)

            self.service.save_point_cloud(result_points, output_path, output_format)

            self._update_task_status_sync(db, task, TaskStatus.RUNNING, progress=90)

            metadata = self.service.extract_metadata(output_path, output_format)

            new_pc = PointCloud(
                name=f"{source.name}-处理结果",
                original_filename=output_filename,
                storage_path=output_path,
                file_format=output_format,
                file_size=Path(output_path).stat().st_size,
                points_count=metadata["points_count"],
                bounding_box=metadata["bounding_box"],
                capture_time=source.capture_time,
                sensor_model=source.sensor_model,
                coordinate_system=source.coordinate_system,
                group_name=source.group_name,
                tags=(source.tags or []) + ["处理结果", processing_type],
                version=source.version + 1,
                created_by=task.created_by,
            )
            db.add(new_pc)
            db.flush()

            task.result_pointcloud_id = new_pc.id
            task.status = TaskStatus.SUCCESS
            task.progress = 100
            task.finished_at = datetime.utcnow()

            db.commit()
            logger.info("任务执行成功: %d, 结果点云ID: %d", task_id, new_pc.id)

        except ProcessingException as e:
            logger.error("处理异常: %s", e.message)
            if task:
                self._update_task_status_sync(db, task, TaskStatus.FAILED, error_message=e.message)
        except MemoryError:
            logger.error("内存不足: %d", task_id)
            if task:
                self._update_task_status_sync(
                    db, task, TaskStatus.FAILED, error_message="内存不足，无法完成处理"
                )
        except Exception as e:
            logger.exception("任务执行异常: %d - %s", task_id, str(e))
            if task:
                self._update_task_status_sync(db, task, TaskStatus.FAILED, error_message=str(e))
        finally:
            db.close()

    def _process_points(
        self,
        points: np.ndarray,
        processing_type: str,
        parameters: dict[str, Any],
    ) -> tuple[np.ndarray, dict[str, Any]]:
        result_points = points
        result_info: dict[str, Any] = {}

        if processing_type == "voxel_grid_filter":
            voxel_size = parameters.get("voxel_size", 0.05)
            result_points = self.service.voxel_grid_filter(points, voxel_size)
            result_info = {"voxel_size": voxel_size, "input_points": len(points), "output_points": len(result_points)}

        elif processing_type == "statistical_outlier_removal":
            nb_neighbors = parameters.get("nb_neighbors", 20)
            std_ratio = parameters.get("std_ratio", 2.0)
            result_points = self.service.statistical_outlier_removal(points, nb_neighbors, std_ratio)
            result_info = {
                "nb_neighbors": nb_neighbors,
                "std_ratio": std_ratio,
                "input_points": len(points),
                "output_points": len(result_points),
            }

        elif processing_type == "radius_outlier_removal":
            radius = parameters.get("radius", 1.0)
            min_neighbors = parameters.get("min_neighbors", 5)
            result_points = self.service.radius_outlier_removal(points, radius, min_neighbors)
            result_info = {
                "radius": radius,
                "min_neighbors": min_neighbors,
                "input_points": len(points),
                "output_points": len(result_points),
            }

        elif processing_type == "plane_segmentation":
            distance_threshold = parameters.get("distance_threshold", 0.01)
            return_inliers = parameters.get("return_inliers", True)
            inliers, outliers, plane_info = self.service.plane_segmentation(points, distance_threshold)
            result_points = inliers if return_inliers else outliers
            result_info = plane_info

        elif processing_type == "icp_registration":
            target_pc_id = parameters.get("target_pointcloud_id")
            if not target_pc_id:
                raise_processing_error(
                    "INVALID_PARAMS",
                    "ICP配准需要指定目标点云ID",
                )

            db = SessionLocal()
            try:
                target_pc = db.query(PointCloud).filter(PointCloud.id == target_pc_id).first()
                if not target_pc:
                    raise_processing_error(
                        "TARGET_NOT_FOUND",
                        f"目标点云不存在: {target_pc_id}",
                    )

                target_points = self.service.load_point_cloud(target_pc.storage_path, target_pc.file_format)
                threshold = parameters.get("threshold", 1.0)
                max_iteration = parameters.get("max_iteration", 100)

                result_points, registration_info = self.service.icp_registration(
                    points, target_points, threshold, max_iteration
                )
                result_info = registration_info
            finally:
                db.close()

        elif processing_type == "downsample":
            voxel_size = parameters.get("voxel_size", 0.1)
            result_points = self.service.voxel_grid_filter(points, voxel_size)
            result_info = {"voxel_size": voxel_size, "input_points": len(points), "output_points": len(result_points)}

        elif processing_type == "denoise":
            nb_neighbors = parameters.get("nb_neighbors", 20)
            std_ratio = parameters.get("std_ratio", 2.0)
            result_points = self.service.statistical_outlier_removal(points, nb_neighbors, std_ratio)
            result_info = {
                "nb_neighbors": nb_neighbors,
                "std_ratio": std_ratio,
                "input_points": len(points),
                "output_points": len(result_points),
            }

        else:
            raise_processing_error(
                "UNSUPPORTED_PROCESSING_TYPE",
                f"不支持的处理类型: {processing_type}",
            )

        return result_points, result_info

    def _update_task_status_sync(
        self,
        db,
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
        except Exception:
            logger.exception("更新任务状态失败")
            db.rollback()

    async def _update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        progress: int = 0,
        error_message: str | None = None,
    ) -> None:
        db = SessionLocal()
        try:
            task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
            if task:
                self._update_task_status_sync(db, task, status, progress, error_message)
        finally:
            db.close()

    async def cancel_task(self, task_id: int) -> bool:
        task = self.running_tasks.get(task_id)
        if task:
            task.cancel()
            logger.info("任务取消请求已发送: %d", task_id)
            return True
        return False

    def get_running_task_count(self) -> int:
        return len(self.running_tasks)


task_manager = BackgroundTaskManager()


async def process_point_cloud_background(
    task_id: int,
    processing_type: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    await task_manager.submit_processing_task(task_id, processing_type, parameters)


async def execute_processing_task(
    task_id: int,
    db_session=None,
) -> None:
    db = db_session or SessionLocal()
    try:
        task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
        if not task:
            logger.error("任务不存在: %s", task_id)
            return

        await process_point_cloud_background(
            task_id,
            task.task_type.value,
            task.parameters,
        )
    finally:
        if not db_session:
            db.close()
