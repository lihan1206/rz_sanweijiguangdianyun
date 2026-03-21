from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func
from typing import Optional
import os
import uuid
from pathlib import Path
import asyncio

from app.core.database import get_db
from app.core.security import get_current_user_id, task_limiter
from app.core.config import settings
from app.models.processing_task import ProcessingTask, TaskType, TaskStatus
from app.models.point_cloud import PointCloud, PointCloudStatus, PointCloudVisibility, FileFormat
from app.models.scene import Scene
from app.utils.schemas import (
    ResponseBase, TaskCreate, TaskResponse, TaskListResponse,
    TaskFilterParams, VoxelFilterParams, StatisticalFilterParams,
    RansacSegmentParams, IcpRegisterParams
)
from app.services.pointcloud_processor import processor

router = APIRouter(prefix="/tasks", tags=["Processing Tasks"])

PROCESSED_DIR = Path(settings.PROCESSED_DIR)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


async def process_task_async(task_id: int, db: AsyncSession):
    """异步处理任务"""
    # 获取任务
    result = await db.execute(
        select(ProcessingTask).where(ProcessingTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return
    
    # 更新状态为运行中
    task.status = TaskStatus.RUNNING
    task.started_at = func.now()
    await db.commit()
    
    try:
        # 获取输入点云
        result = await db.execute(
            select(PointCloud).where(PointCloud.id == task.point_cloud_id)
        )
        input_pc = result.scalar_one_or_none()
        
        if not input_pc or not os.path.exists(input_pc.file_path):
            raise ValueError("Input point cloud not found")
        
        # 生成输出文件路径
        output_id = str(uuid.uuid4())
        output_path = PROCESSED_DIR / f"{output_id}.ply"
        
        # 执行处理
        summary = processor.process_task(
            task.task_type.value,
            input_pc.file_path,
            str(output_path),
            task.parameters
        )
        
        # 解析结果点云
        result_pcd = processor.load_point_cloud(str(output_path))
        result_info = processor.get_point_cloud_info(result_pcd)
        
        # 创建结果点云记录
        result_pc = PointCloud(
            user_id=task.user_id,
            scene_id=task.scene_id,
            name=f"{input_pc.name}_{task.task_type.value}",
            description=f"Processed from {input_pc.name} using {task.task_type.value}",
            original_filename=f"{output_id}.ply",
            file_path=str(output_path),
            file_size=os.path.getsize(output_path),
            file_format=FileFormat.PLY,
            point_count=result_info["point_count"],
            bounding_box=result_info["bounding_box"],
            has_color=result_info["has_color"],
            has_normal=result_info["has_normal"],
            status=PointCloudStatus.READY,
            visibility=PointCloudVisibility.PRIVATE,
            parent_id=input_pc.id
        )
        
        db.add(result_pc)
        await db.flush()
        
        # 更新任务
        task.status = TaskStatus.COMPLETED
        task.result_point_cloud_id = result_pc.id
        task.result_summary = summary
        task.progress = 100
        task.completed_at = func.now()
        
        # 计算实际耗时
        if task.started_at:
            from datetime import datetime
            task.actual_duration = int((datetime.utcnow() - task.started_at).total_seconds())
        
        await db.commit()
        
    except Exception as e:
        # 更新失败状态
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        task.completed_at = func.now()
        await db.commit()


@router.post("", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: Request,
    task_data: TaskCreate,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """创建处理任务"""
    # 限流检查
    client_ip = request.client.host
    if not task_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Task creation rate limit exceeded"
        )
    
    # 检查点云是否存在
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == task_data.point_cloud_id)
    )
    point_cloud = result.scalar_one_or_none()
    
    if not point_cloud:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Point cloud not found"
        )
    
    # 检查权限
    if point_cloud.user_id != user_id and point_cloud.visibility == PointCloudVisibility.PRIVATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # 检查场景（如果指定）
    if task_data.scene_id:
        result = await db.execute(
            select(Scene).where(Scene.id == task_data.scene_id)
        )
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scene not found"
            )
    
    # 验证参数
    try:
        if task_data.task_type == TaskType.FILTER_VOXEL:
            VoxelFilterParams(**task_data.parameters)
        elif task_data.task_type == TaskType.FILTER_STATISTICAL:
            StatisticalFilterParams(**task_data.parameters)
        elif task_data.task_type == TaskType.SEGMENT_RANSAC:
            RansacSegmentParams(**task_data.parameters)
        elif task_data.task_type == TaskType.REGISTER_ICP:
            params = IcpRegisterParams(**task_data.parameters)
            # 检查目标点云
            result = await db.execute(
                select(PointCloud).where(PointCloud.id == params.target_point_cloud_id)
            )
            target_pc = result.scalar_one_or_none()
            if not target_pc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target point cloud not found"
                )
            # 添加目标路径到参数
            task_data.parameters["target_path"] = target_pc.file_path
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameters: {str(e)}"
        )
    
    # 创建任务
    task = ProcessingTask(
        point_cloud_id=task_data.point_cloud_id,
        user_id=user_id,
        scene_id=task_data.scene_id,
        task_type=task_data.task_type,
        task_name=task_data.task_name or f"{task_data.task_type.value}_{point_cloud.name}",
        status=TaskStatus.PENDING,
        priority=task_data.priority,
        parameters=task_data.parameters,
        estimated_duration=60  # 预估60秒
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # 启动后台任务
    background_tasks.add_task(process_task_async, task.id, db)
    
    return ResponseBase(
        code=201,
        message="Task created",
        data=task.to_dict()
    )


@router.get("", response_model=ResponseBase)
async def list_tasks(
    params: TaskFilterParams = Depends(),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取任务列表"""
    # 构建查询
    query = select(ProcessingTask).where(ProcessingTask.user_id == user_id)
    
    # 应用过滤条件
    if params.status:
        query = query.where(ProcessingTask.status == params.status)
    if params.point_cloud_id:
        query = query.where(ProcessingTask.point_cloud_id == params.point_cloud_id)
    if params.scene_id:
        query = query.where(ProcessingTask.scene_id == params.scene_id)
    
    # 排序（按创建时间倒序）
    query = query.order_by(desc(ProcessingTask.created_at))
    
    # 分页
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()
    
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return ResponseBase(
        code=200,
        data={
            "items": [task.to_dict() for task in tasks],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "pages": (total + params.page_size - 1) // params.page_size
        }
    )


@router.get("/{task_id}", response_model=ResponseBase)
async def get_task(
    task_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取任务详情"""
    result = await db.execute(
        select(ProcessingTask).where(ProcessingTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # 检查权限
    if task.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return ResponseBase(
        code=200,
        data=task.to_dict(include_point_cloud=True)
    )


@router.post("/{task_id}/cancel", response_model=ResponseBase)
async def cancel_task(
    task_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """取消任务"""
    result = await db.execute(
        select(ProcessingTask).where(ProcessingTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # 检查权限
    if task.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # 只能取消待处理或队列中的任务
    if task.status not in [TaskStatus.PENDING, TaskStatus.QUEUED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task.status.value}"
        )
    
    task.status = TaskStatus.CANCELLED
    await db.commit()
    
    return ResponseBase(
        code=200,
        message="Task cancelled"
    )


@router.get("/types", response_model=ResponseBase)
async def get_task_types():
    """获取支持的任务类型"""
    return ResponseBase(
        code=200,
        data={
            "types": [
                {
                    "type": "filter_voxel",
                    "name": "Voxel Grid Filter",
                    "description": "Downsample point cloud using voxel grid",
                    "parameters": {
                        "voxel_size": {"type": "float", "default": 0.05, "min": 0.001, "description": "Voxel size"}
                    }
                },
                {
                    "type": "filter_statistical",
                    "name": "Statistical Outlier Removal",
                    "description": "Remove outliers using statistical analysis",
                    "parameters": {
                        "nb_neighbors": {"type": "int", "default": 20, "min": 1, "description": "Number of neighbors"},
                        "std_ratio": {"type": "float", "default": 2.0, "min": 0.1, "description": "Standard deviation ratio"}
                    }
                },
                {
                    "type": "segment_ransac",
                    "name": "RANSAC Plane Segmentation",
                    "description": "Segment planes using RANSAC algorithm",
                    "parameters": {
                        "distance_threshold": {"type": "float", "default": 0.01, "min": 0.0001, "description": "Distance threshold"},
                        "ransac_n": {"type": "int", "default": 3, "min": 3, "description": "Number of points to sample"},
                        "num_iterations": {"type": "int", "default": 1000, "min": 1, "description": "Number of iterations"}
                    }
                },
                {
                    "type": "register_icp",
                    "name": "ICP Registration",
                    "description": "Register point cloud to target using ICP",
                    "parameters": {
                        "target_point_cloud_id": {"type": "int", "required": True, "description": "Target point cloud ID"},
                        "max_correspondence_distance": {"type": "float", "default": 0.05, "min": 0.001, "description": "Max correspondence distance"},
                        "max_iterations": {"type": "int", "default": 30, "min": 1, "description": "Max iterations"}
                    }
                }
            ]
        }
    )
