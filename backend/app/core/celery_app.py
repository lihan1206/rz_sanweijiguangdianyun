from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "pointcloud_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.task_timeout,
    task_soft_time_limit=settings.task_timeout - 60,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)

# 自动发现任务
celery.autodiscover_tasks(["app.services"])
