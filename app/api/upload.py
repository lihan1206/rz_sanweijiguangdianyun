import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, Form, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.core.security import get_current_user_id
from app.core.exceptions import (
    FileUploadError, FileTooLargeError, InvalidFileTypeError,
    DatabaseError, NotFoundError, handle_exception
)
from app.db.database import get_db
from app.db.models import PointCloud, ProcessingJob, JobStatus, ProcessingType
from app.services.point_cloud_service import point_cloud_service
from app.background_tasks import process_point_cloud_task

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["upload"])
settings = get_settings()

# 支持的文件格式
ALLOWED_EXTENSIONS = {'.las', '.laz', '.ply', '.pcd', '.xyz', '.pts'}


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@router.post("/upload")
async def upload_point_cloud(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    processing_type: Optional[str] = Form(None),
    processing_params: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    上传点云文件
    
    - **file**: 点云文件 (.las, .laz, .ply, .pcd, .xyz, .pts)
    - **processing_type**: 处理类型 (filter, segment, register, downsample)
    - **processing_params**: 处理参数 (JSON 字符串)
    """
    start_time = datetime.utcnow()
    
    try:
        # 检查文件是否存在
        if not file:
            raise FileUploadError("未提供文件")
        
        filename = file.filename
        logger.info(f"用户 {current_user_id} 开始上传文件: {filename}")
        
        # 检查文件类型
        if not allowed_file(filename):
            raise InvalidFileTypeError(
                f"不支持的文件类型",
                details={
                    "filename": filename,
                    "allowed_extensions": list(ALLOWED_EXTENSIONS)
                }
            )
        
        # 生成唯一文件名
        file_ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = Path(settings.upload_dir) / unique_filename
        
        # 保存文件
        file_size = 0
        try:
            with open(file_path, "wb") as buffer:
                while chunk := await file.read(8192):  # 8KB 分块读取
                    file_size += len(chunk)
                    
                    # 检查文件大小
                    if file_size > settings.max_file_size:
                        buffer.close()
                        os.remove(file_path)
                        raise FileTooLargeError(
                            f"文件大小超过限制",
                            details={
                                "max_size": settings.max_file_size,
                                "file_size": file_size
                            }
                        )
                    
                    buffer.write(chunk)
            
            logger.info(f"文件保存成功: {file_path}, 大小: {file_size} bytes")
            
        except Exception as e:
            if file_path.exists():
                os.remove(file_path)
            logger.error(f"文件保存失败: {str(e)}")
            raise FileUploadError(f"文件保存失败: {str(e)}")
        
        finally:
            await file.close()
        
        # 获取点云信息
        try:
            import open3d as o3d
            pcd = await point_cloud_service.read_point_cloud(str(file_path))
            point_count = len(pcd.points)
            bbox = pcd.get_axis_aligned_bounding_box()
            bbox_min = bbox.min_bound.tolist()
            bbox_max = bbox.max_bound.tolist()
        except Exception as e:
            logger.warning(f"读取点云信息失败: {str(e)}")
            point_count = None
            bbox_min = None
            bbox_max = None
        
        # 创建数据库记录
        try:
            point_cloud = PointCloud(
                name=unique_filename,
                original_filename=filename,
                file_path=str(file_path),
                file_size=file_size,
                file_format=file_ext.lstrip('.'),
                point_count=point_count,
                bbox_min_x=bbox_min[0] if bbox_min else None,
                bbox_min_y=bbox_min[1] if bbox_min else None,
                bbox_min_z=bbox_min[2] if bbox_min else None,
                bbox_max_x=bbox_max[0] if bbox_max else None,
                bbox_max_y=bbox_max[1] if bbox_max else None,
                bbox_max_z=bbox_max[2] if bbox_max else None,
                owner_id=current_user_id
            )
            db.add(point_cloud)
            db.commit()
            db.refresh(point_cloud)
            
            logger.info(f"点云记录创建成功: ID={point_cloud.id}")
            
        except Exception as e:
            if file_path.exists():
                os.remove(file_path)
            logger.error(f"数据库操作失败: {str(e)}")
            raise DatabaseError(f"保存点云信息失败: {str(e)}")
        
        # 如果指定了处理类型，创建处理任务
        processing_job = None
        if processing_type:
            try:
                proc_type = ProcessingType(processing_type)
                
                # 解析处理参数
                import json
                params = {}
                if processing_params:
                    try:
                        params = json.loads(processing_params)
                    except json.JSONDecodeError:
                        logger.warning(f"处理参数解析失败: {processing_params}")
                
                processing_job = ProcessingJob(
                    job_name=f"Process {filename}",
                    processing_type=proc_type,
                    status=JobStatus.PENDING,
                    progress=0.0,
                    point_cloud_id=point_cloud.id,
                    owner_id=current_user_id,
                    parameters=params
                )
                db.add(processing_job)
                db.commit()
                db.refresh(processing_job)
                
                logger.info(f"处理任务创建成功: ID={processing_job.id}")
                
                # 启动后台处理任务
                background_tasks.add_task(
                    process_point_cloud_task,
                    processing_job.id
                )
                
            except ValueError:
                logger.warning(f"无效的处理类型: {processing_type}")
            except Exception as e:
                logger.error(f"创建处理任务失败: {str(e)}")
        
        upload_duration = (datetime.utcnow() - start_time).total_seconds()
        
        response_data = {
            "success": True,
            "message": "文件上传成功",
            "data": {
                "point_cloud": {
                    "id": point_cloud.id,
                    "name": point_cloud.name,
                    "original_filename": point_cloud.original_filename,
                    "file_size": point_cloud.file_size,
                    "file_format": point_cloud.file_format,
                    "point_count": point_cloud.point_count,
                    "created_at": point_cloud.created_at.isoformat() if point_cloud.created_at else None
                },
                "upload_duration": upload_duration
            }
        }
        
        if processing_job:
            response_data["data"]["processing_job"] = {
                "id": processing_job.id,
                "type": processing_job.processing_type.value,
                "status": processing_job.status.value,
                "created_at": processing_job.created_at.isoformat() if processing_job.created_at else None
            }
        
        return JSONResponse(content=response_data)
        
    except (FileUploadError, FileTooLargeError, InvalidFileTypeError, DatabaseError) as e:
        logger.error(f"上传失败: {e.message}")
        raise handle_exception(e)
        
    except Exception as e:
        logger.error(f"上传过程中发生未知错误: {str(e)}")
        raise handle_exception(FileUploadError(f"上传失败: {str(e)}"))


@router.get("/uploads")
async def list_uploads(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取当前用户的点云文件列表"""
    try:
        point_clouds = db.query(PointCloud).filter(
            PointCloud.owner_id == current_user_id
        ).order_by(PointCloud.created_at.desc()).offset(skip).limit(limit).all()
        
        total = db.query(PointCloud).filter(
            PointCloud.owner_id == current_user_id
        ).count()
        
        return {
            "success": True,
            "data": {
                "items": [pc.to_dict() for pc in point_clouds],
                "total": total,
                "skip": skip,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"获取上传列表失败: {str(e)}")
        raise handle_exception(DatabaseError(f"获取列表失败: {str(e)}"))


@router.get("/uploads/{point_cloud_id}")
async def get_upload(
    point_cloud_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取点云文件详情"""
    try:
        point_cloud = db.query(PointCloud).filter(
            PointCloud.id == point_cloud_id,
            PointCloud.owner_id == current_user_id
        ).first()
        
        if not point_cloud:
            raise NotFoundError(f"点云文件不存在: {point_cloud_id}")
        
        # 获取关联的处理任务
        jobs = db.query(ProcessingJob).filter(
            ProcessingJob.point_cloud_id == point_cloud_id
        ).all()
        
        return {
            "success": True,
            "data": {
                "point_cloud": point_cloud.to_dict(),
                "processing_jobs": [job.to_dict() for job in jobs]
            }
        }
        
    except NotFoundError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"获取点云详情失败: {str(e)}")
        raise handle_exception(DatabaseError(f"获取详情失败: {str(e)}"))


@router.delete("/uploads/{point_cloud_id}")
async def delete_upload(
    point_cloud_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """删除点云文件"""
    try:
        point_cloud = db.query(PointCloud).filter(
            PointCloud.id == point_cloud_id,
            PointCloud.owner_id == current_user_id
        ).first()
        
        if not point_cloud:
            raise NotFoundError(f"点云文件不存在: {point_cloud_id}")
        
        # 删除物理文件
        file_path = Path(point_cloud.file_path)
        if file_path.exists():
            file_path.unlink()
        
        # 删除处理后的文件
        if point_cloud.processed_file_path:
            processed_path = Path(point_cloud.processed_file_path)
            if processed_path.exists():
                processed_path.unlink()
        
        # 删除关联的处理结果文件
        jobs = db.query(ProcessingJob).filter(
            ProcessingJob.point_cloud_id == point_cloud_id
        ).all()
        
        for job in jobs:
            if job.result_data and "output_file" in job.result_data:
                output_path = Path(job.result_data["output_file"])
                if output_path.exists():
                    output_path.unlink()
        
        # 删除数据库记录
        db.delete(point_cloud)
        db.commit()
        
        logger.info(f"点云文件已删除: {point_cloud_id}")
        
        return {
            "success": True,
            "message": "文件删除成功"
        }
        
    except NotFoundError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"删除点云文件失败: {str(e)}")
        raise handle_exception(DatabaseError(f"删除失败: {str(e)}"))
