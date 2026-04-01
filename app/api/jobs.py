from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.security import get_current_user_id
from app.core.exceptions import NotFoundError, handle_exception
from app.db.database import get_db
from app.db.models import ProcessingJob, JobStatus, PointCloud

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/")
async def list_jobs(
    status: Optional[str] = None,
    processing_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取处理任务列表"""
    try:
        query = db.query(ProcessingJob).filter(
            ProcessingJob.owner_id == current_user_id
        )
        
        if status:
            try:
                job_status = JobStatus(status)
                query = query.filter(ProcessingJob.status == job_status)
            except ValueError:
                pass
        
        if processing_type:
            query = query.filter(ProcessingJob.processing_type == processing_type)
        
        total = query.count()
        jobs = query.order_by(ProcessingJob.created_at.desc()).offset(skip).limit(limit).all()
        
        return {
            "success": True,
            "data": {
                "items": [job.to_dict() for job in jobs],
                "total": total,
                "skip": skip,
                "limit": limit
            }
        }
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取任务详情"""
    try:
        job = db.query(ProcessingJob).filter(
            ProcessingJob.id == job_id,
            ProcessingJob.owner_id == current_user_id
        ).first()
        
        if not job:
            raise NotFoundError(f"任务不存在: {job_id}")
        
        return {
            "success": True,
            "data": job.to_dict()
        }
        
    except NotFoundError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {str(e)}")


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """取消处理任务"""
    try:
        job = db.query(ProcessingJob).filter(
            ProcessingJob.id == job_id,
            ProcessingJob.owner_id == current_user_id
        ).first()
        
        if not job:
            raise NotFoundError(f"任务不存在: {job_id}")
        
        if job.status not in [JobStatus.PENDING, JobStatus.PROCESSING]:
            return {
                "success": False,
                "message": f"任务状态为 {job.status.value}，无法取消"
            }
        
        job.status = JobStatus.CANCELLED
        db.commit()
        
        logger.info(f"任务已取消: {job_id}")
        
        return {
            "success": True,
            "message": "任务已取消",
            "data": job.to_dict()
        }
        
    except NotFoundError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"取消任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """删除处理任务"""
    try:
        job = db.query(ProcessingJob).filter(
            ProcessingJob.id == job_id,
            ProcessingJob.owner_id == current_user_id
        ).first()
        
        if not job:
            raise NotFoundError(f"任务不存在: {job_id}")
        
        # 删除处理结果文件
        if job.result_data and "output_file" in job.result_data:
            from pathlib import Path
            output_path = Path(job.result_data["output_file"])
            if output_path.exists():
                output_path.unlink()
        
        db.delete(job)
        db.commit()
        
        logger.info(f"任务已删除: {job_id}")
        
        return {
            "success": True,
            "message": "任务已删除"
        }
        
    except NotFoundError as e:
        raise handle_exception(e)
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")


@router.get("/stats/summary")
async def get_jobs_stats(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取任务统计信息"""
    try:
        from sqlalchemy import func
        
        stats = db.query(
            ProcessingJob.status,
            func.count(ProcessingJob.id).label("count")
        ).filter(
            ProcessingJob.owner_id == current_user_id
        ).group_by(ProcessingJob.status).all()
        
        status_counts = {status.value: 0 for status in JobStatus}
        for status, count in stats:
            status_counts[status.value] = count
        
        # 获取处理类型统计
        type_stats = db.query(
            ProcessingJob.processing_type,
            func.count(ProcessingJob.id).label("count")
        ).filter(
            ProcessingJob.owner_id == current_user_id
        ).group_by(ProcessingJob.processing_type).all()
        
        type_counts = {proc_type.value: count for proc_type, count in type_stats}
        
        return {
            "success": True,
            "data": {
                "by_status": status_counts,
                "by_type": type_counts,
                "total": sum(status_counts.values())
            }
        }
        
    except Exception as e:
        logger.error(f"获取任务统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务统计失败: {str(e)}")
