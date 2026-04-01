from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import TaskCreateRequest, TaskCreateResponse, TaskDetail, TaskStatusResponse
from app.services.audit import write_audit_log
from app.services.celery_tasks import process_pointcloud

router = APIRouter(prefix="/tasks", tags=["处理任务"])
settings = get_settings()


@router.get("", response_model=list[TaskListItem])
def list_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TaskListItem]:
    records = db.query(ProcessingTask).order_by(ProcessingTask.created_at.desc()).all()
    return [TaskListItem.model_validate(item) for item in records]


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TaskDetail:
    """获取单个任务详情"""
    task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskDetail.model_validate(task)


@router.get("/status/{celery_task_id}", response_model=TaskStatusResponse)
def get_celery_task_status(
    celery_task_id: str,
    _: User = Depends(get_current_user),
) -> TaskStatusResponse:
    """获取 Celery 任务状态"""
    from app.core.celery_app import celery
    
    task_result = celery.AsyncResult(celery_task_id)
    
    status_map = {
        "PENDING": "pending",
        "STARTED": "running",
        "SUCCESS": "success",
        "FAILURE": "failed",
        "REVOKED": "failed",
    }
    
    return TaskStatusResponse(
        task_id=celery_task_id,
        status=status_map.get(task_result.status, "unknown"),
        result=task_result.result if task_result.successful() else None,
        error=str(task_result.result) if task_result.failed() else None
    )


@router.post("", response_model=TaskCreateResponse)
def create_task(
    payload: TaskCreateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> TaskCreateResponse:
    pointcloud = db.query(PointCloud).filter(PointCloud.id == payload.pointcloud_id).first()
    if not pointcloud:
        raise HTTPException(status_code=404, detail="源点云不存在")

    task = ProcessingTask(
        pointcloud_id=payload.pointcloud_id,
        session_id=payload.session_id,
        task_type=payload.task_type,
        parameters=payload.parameters,
        output_format=payload.output_format,
        priority=payload.priority,
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
        detail={"task_type": payload.task_type.value, "pointcloud_id": payload.pointcloud_id},
    )

    db.commit()
    
    # 使用 Celery 异步执行任务
    celery_task = process_pointcloud.delay(task.id, settings.upload_dir)
    
    return TaskCreateResponse(
        id=task.id,
        celery_task_id=celery_task.id,
        status=TaskStatus.PENDING,
        message="任务已提交"
    )
