"""
Celery配置 - 用于后台任务处理
"""
import os
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建Celery应用
celery_app = Celery(
    'pointcloud_processor',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2'),
    include=['app.services.pointcloud_processor']
)

# Celery配置
celery_app.conf.update(
    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    
    # 任务执行设置
    task_track_started=True,
    task_time_limit=3600,  # 任务超时时间1小时
    task_soft_time_limit=3300,  # 软超时55分钟
    
    # 结果存储设置
    result_expires=86400,  # 结果保留24小时
    result_extended=True,
    
    # 并发设置
    worker_prefetch_multiplier=1,  # 每个worker一次只取一个任务
    worker_max_tasks_per_child=50,  # 每个worker子进程处理50个任务后重启
    
    # 队列设置
    task_default_queue='default',
    task_queues={
        'default': {
            'exchange': 'default',
            'routing_key': 'default'
        },
        'processing': {
            'exchange': 'processing',
            'routing_key': 'processing'
        },
        'ai_detection': {
            'exchange': 'ai_detection',
            'routing_key': 'ai_detection'
        }
    },
    task_routes={
        'app.services.pointcloud_processor.*': {'queue': 'processing'},
        'app.services.ai_detector.*': {'queue': 'ai_detection'}
    },
    
    # 定时任务
    beat_schedule={
        'cleanup-old-files': {
            'task': 'app.celery_app.cleanup_old_files',
            'schedule': 3600.0,  # 每小时执行一次
        },
        'update-task-status': {
            'task': 'app.celery_app.update_task_status',
            'schedule': 60.0,  # 每分钟执行一次
        }
    }
)


@task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **extras):
    """任务开始前的处理"""
    logger.info(f"Task {task.name}[{task_id}] started")


@task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, state, **extras):
    """任务完成后的处理"""
    logger.info(f"Task {task.name}[{task_id}] finished with state: {state}")


@task_failure.connect
def task_failure_handler(task_id, exception, args, kwargs, traceback, einfo, **extras):
    """任务失败时的处理"""
    logger.error(f"Task failed: {task_id}, Exception: {exception}")


@celery_app.task(bind=True)
def cleanup_old_files(self):
    """清理过期文件"""
    import asyncio
    from datetime import datetime, timedelta
    from app.models.database import AsyncSessionLocal
    from app.models.models import PointCloud
    from sqlalchemy import select, and_
    
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            # 删除30天前的已删除点云
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            stmt = select(PointCloud).where(
                and_(
                    PointCloud.status == 'deleted',
                    PointCloud.updated_at < cutoff_date
                )
            )
            result = await db.execute(stmt)
            old_clouds = result.scalars().all()
            
            for cloud in old_clouds:
                # 删除物理文件
                import os
                if cloud.file_path and os.path.exists(cloud.file_path):
                    try:
                        os.remove(cloud.file_path)
                        logger.info(f"Deleted old file: {cloud.file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete file {cloud.file_path}: {e}")
                
                # 从数据库删除记录
                await db.delete(cloud)
            
            await db.commit()
            return f"Cleaned up {len(old_clouds)} old files"
    
    return asyncio.run(_cleanup())


@celery_app.task(bind=True)
def update_task_status(self):
    """更新任务状态 - 检查超时任务"""
    import asyncio
    from datetime import datetime, timedelta
    from app.models.database import AsyncSessionLocal
    from app.models.models import ProcessingTask
    from sqlalchemy import select, and_
    
    async def _update():
        async with AsyncSessionLocal() as db:
            # 标记运行超过2小时的任务为失败
            cutoff_time = datetime.utcnow() - timedelta(hours=2)
            stmt = select(ProcessingTask).where(
                and_(
                    ProcessingTask.status == 'running',
                    ProcessingTask.started_at < cutoff_time
                )
            )
            result = await db.execute(stmt)
            timeout_tasks = result.scalars().all()
            
            for task in timeout_tasks:
                task.status = 'failed'
                task.error_message = 'Task timeout (exceeded 2 hours)'
                task.completed_at = datetime.utcnow()
                logger.warning(f"Task {task.id} marked as timeout")
            
            await db.commit()
            return f"Updated {len(timeout_tasks)} timeout tasks"
    
    return asyncio.run(_update())


if __name__ == '__main__':
    celery_app.start()
