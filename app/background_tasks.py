import asyncio
import time
from typing import Optional, Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.config import get_settings
from app.core.exceptions import ProcessingError, TimeoutError
from app.db.database import get_db_context
from app.db.models import ProcessingJob, JobStatus, PointCloud
from app.services.point_cloud_service import point_cloud_service

logger = get_logger(__name__)
settings = get_settings()


async def update_job_progress(
    job_id: int,
    progress: float,
    status: Optional[JobStatus] = None,
    result_data: Optional[dict] = None,
    error_message: Optional[str] = None
) -> None:
    """更新任务进度"""
    try:
        with get_db_context() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if not job:
                logger.error(f"任务不存在: {job_id}")
                return
            
            job.progress = min(progress, 100.0)
            
            if status:
                job.status = status
                if status == JobStatus.PROCESSING and not job.started_at:
                    job.started_at = datetime.utcnow()
                elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    job.completed_at = datetime.utcnow()
                    if job.started_at:
                        job.processing_duration = (
                            job.completed_at - job.started_at
                        ).total_seconds()
            
            if result_data is not None:
                job.result_data = result_data
            
            if error_message is not None:
                job.error_message = error_message
            
            db.commit()
            logger.debug(f"任务 {job_id} 进度更新: {progress}%")
    except Exception as e:
        logger.error(f"更新任务进度失败: {job_id}, 错误: {str(e)}")


async def process_point_cloud_task(
    job_id: int,
    timeout: Optional[int] = None
) -> None:
    """
    异步处理点云任务
    
    Args:
        job_id: 处理任务ID
        timeout: 超时时间（秒），默认使用配置中的 processing_timeout
    """
    if timeout is None:
        timeout = settings.processing_timeout
    
    start_time = time.time()
    
    try:
        # 获取任务信息
        with get_db_context() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if not job:
                raise ProcessingError(f"任务不存在: {job_id}")
            
            if job.status != JobStatus.PENDING:
                logger.warning(f"任务 {job_id} 状态不是 PENDING，跳过处理")
                return
            
            # 更新状态为处理中
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
            db.commit()
        
        logger.info(f"开始处理点云任务: {job_id}")
        
        # 创建进度回调
        async def progress_callback(progress: float):
            await update_job_progress(job_id, progress)
        
        # 使用 asyncio.wait_for 实现超时控制
        try:
            result = await asyncio.wait_for(
                point_cloud_service.process_point_cloud(job, progress_callback),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"点云处理超时（{timeout}秒）")
        
        # 更新任务完成状态
        await update_job_progress(
            job_id=job_id,
            progress=100.0,
            status=JobStatus.COMPLETED,
            result_data=result
        )
        
        # 更新点云处理状态
        with get_db_context() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job and job.result_data and "output_file" in job.result_data:
                point_cloud = db.query(PointCloud).filter(
                    PointCloud.id == job.point_cloud_id
                ).first()
                if point_cloud:
                    point_cloud.is_processed = True
                    point_cloud.processed_file_path = job.result_data["output_file"]
                    db.commit()
        
        elapsed_time = time.time() - start_time
        logger.info(f"点云任务 {job_id} 处理完成，耗时: {elapsed_time:.2f}秒")
        
    except TimeoutError as e:
        logger.error(f"点云任务 {job_id} 超时: {str(e)}")
        await update_job_progress(
            job_id=job_id,
            progress=0,
            status=JobStatus.FAILED,
            error_message=f"处理超时: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"点云任务 {job_id} 处理失败: {str(e)}")
        await update_job_progress(
            job_id=job_id,
            progress=0,
            status=JobStatus.FAILED,
            error_message=str(e)
        )


async def cleanup_old_files(
    max_age_days: int = 7,
    dry_run: bool = False
) -> dict:
    """
    清理旧的上传和处理文件
    
    Args:
        max_age_days: 文件最大保留天数
        dry_run: 如果为 True，只返回要删除的文件列表而不实际删除
    
    Returns:
        清理结果统计
    """
    from datetime import timedelta
    
    result = {
        "uploads_deleted": 0,
        "processed_deleted": 0,
        "uploads_errors": [],
        "processed_errors": [],
        "dry_run": dry_run
    }
    
    cutoff_time = time.time() - (max_age_days * 24 * 3600)
    
    # 清理上传目录
    upload_dir = Path(settings.upload_dir)
    if upload_dir.exists():
        for file_path in upload_dir.iterdir():
            if file_path.is_file():
                try:
                    file_stat = file_path.stat()
                    if file_stat.st_mtime < cutoff_time:
                        if not dry_run:
                            file_path.unlink()
                        result["uploads_deleted"] += 1
                        logger.info(f"{'[Dry Run] ' if dry_run else ''}删除旧上传文件: {file_path}")
                except Exception as e:
                    result["uploads_errors"].append(str(file_path))
                    logger.error(f"删除文件失败: {file_path}, 错误: {str(e)}")
    
    # 清理处理结果目录
    processed_dir = Path(settings.processed_dir)
    if processed_dir.exists():
        for file_path in processed_dir.iterdir():
            if file_path.is_file():
                try:
                    file_stat = file_path.stat()
                    if file_stat.st_mtime < cutoff_time:
                        if not dry_run:
                            file_path.unlink()
                        result["processed_deleted"] += 1
                        logger.info(f"{'[Dry Run] ' if dry_run else ''}删除旧处理文件: {file_path}")
                except Exception as e:
                    result["processed_errors"].append(str(file_path))
                    logger.error(f"删除文件失败: {file_path}, 错误: {str(e)}")
    
    return result


async def retry_failed_jobs(
    max_retries: int = 3,
    older_than_minutes: int = 5
) -> dict:
    """
    重试失败的任务
    
    Args:
        max_retries: 最大重试次数
        older_than_minutes: 只重试指定分钟数之前失败的任务
    
    Returns:
        重试结果统计
    """
    from datetime import timedelta
    
    result = {
        "retried": 0,
        "skipped": 0,
        "errors": []
    }
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    
    try:
        with get_db_context() as db:
            # 查找失败且可以重试的任务
            failed_jobs = db.query(ProcessingJob).filter(
                ProcessingJob.status == JobStatus.FAILED,
                ProcessingJob.created_at < cutoff_time
            ).all()
            
            for job in failed_jobs:
                # 检查重试次数（通过 result_data 中的 retry_count）
                retry_count = job.result_data.get("retry_count", 0) if job.result_data else 0
                
                if retry_count >= max_retries:
                    result["skipped"] += 1
                    continue
                
                # 重置任务状态
                job.status = JobStatus.PENDING
                job.progress = 0
                job.error_message = None
                if job.result_data is None:
                    job.result_data = {}
                job.result_data["retry_count"] = retry_count + 1
                job.result_data["last_retry"] = datetime.utcnow().isoformat()
                
                db.commit()
                
                # 启动异步处理
                asyncio.create_task(process_point_cloud_task(job.id))
                
                result["retried"] += 1
                logger.info(f"重试任务: {job.id}, 第 {retry_count + 1} 次重试")
                
    except Exception as e:
        logger.error(f"重试失败任务时出错: {str(e)}")
        result["errors"].append(str(e))
    
    return result


# 后台任务调度器
class BackgroundTaskScheduler:
    def __init__(self):
        self.tasks = []
        self.running = False
    
    async def start(self):
        """启动后台任务调度器"""
        self.running = True
        logger.info("后台任务调度器已启动")
        
        # 启动定期清理任务
        asyncio.create_task(self._cleanup_loop())
        
        # 启动失败任务重试
        asyncio.create_task(self._retry_loop())
    
    async def stop(self):
        """停止后台任务调度器"""
        self.running = False
        logger.info("后台任务调度器已停止")
    
    async def _cleanup_loop(self):
        """定期清理循环"""
        while self.running:
            try:
                await asyncio.sleep(24 * 3600)  # 每天执行一次
                if self.running:
                    result = await cleanup_old_files(max_age_days=7)
                    logger.info(f"文件清理完成: {result}")
            except Exception as e:
                logger.error(f"文件清理任务出错: {str(e)}")
    
    async def _retry_loop(self):
        """失败任务重试循环"""
        while self.running:
            try:
                await asyncio.sleep(300)  # 每5分钟执行一次
                if self.running:
                    result = await retry_failed_jobs()
                    if result["retried"] > 0:
                        logger.info(f"失败任务重试完成: {result}")
            except Exception as e:
                logger.error(f"失败任务重试出错: {str(e)}")


# 全局调度器实例
scheduler = BackgroundTaskScheduler()
