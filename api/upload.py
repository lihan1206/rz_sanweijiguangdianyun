import os
import uuid
import shutil
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from database import get_db
from models import User, PointCloud, ProcessingJob, ProcessingStatus
from api.auth import get_current_active_user
from services.point_cloud_service import PointCloudService, PointCloudProcessingError
from background_tasks import task_manager, PROCESSING_TIMEOUT

load_dotenv()

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 52428800))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
ALLOWED_EXTENSIONS = os.getenv("ALLOWED_EXTENSIONS", ".las,.ply").split(',')

router = APIRouter(prefix="/api", tags=["upload"])

class UploadResponse(BaseModel):
    message: str
    file_id: int
    filename: str
    file_size: int
    job_id: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    start_time: Optional[str]
    duration: Optional[float]
    result: Optional[dict]
    error: Optional[str]

def validate_file(file: UploadFile) -> None:
    """验证上传文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

async def save_upload_file(file: UploadFile, user_id: int) -> tuple[str, str, int]:
    """保存上传的文件"""
    try:
        user_upload_dir = os.path.join(UPLOAD_DIR, f"user_{user_id}")
        os.makedirs(user_upload_dir, exist_ok=True)
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(user_upload_dir, unique_filename)
        
        file_size = 0
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    buffer.close()
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size: {MAX_FILE_SIZE / 1024 / 1024} MB"
                    )
                buffer.write(chunk)
        
        return file_path, unique_filename, file_size
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

def create_point_cloud_record(
    db: Session,
    user_id: int,
    original_filename: str,
    unique_filename: str,
    file_path: str,
    file_size: int
) -> PointCloud:
    """创建点云数据库记录"""
    file_ext = os.path.splitext(original_filename)[1].lower().lstrip('.')
    
    point_cloud = PointCloud(
        filename=unique_filename,
        original_filename=original_filename,
        file_path=file_path,
        file_size=file_size,
        file_format=file_ext,
        user_id=user_id
    )
    db.add(point_cloud)
    db.commit()
    db.refresh(point_cloud)
    
    return point_cloud

def process_point_cloud_task(
    input_path: str,
    output_dir: str,
    point_cloud_id: int,
    job_id: str,
    user_id: int,
    operations: list = None
) -> dict:
    """点云处理任务"""
    from database import SessionLocal
    db = SessionLocal()
    
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
        if job:
            job.status = ProcessingStatus.PROCESSING
            job.updated_at = datetime.utcnow()
            db.commit()
        
        results = PointCloudService.process_point_cloud(
            input_path=input_path,
            output_dir=output_dir,
            operations=operations
        )
        
        if job:
            job.status = ProcessingStatus.COMPLETED
            job.result_path = output_dir
            job.completed_at = datetime.utcnow()
            job.point_count_before = results.get('metadata', {}).get('point_count')
            job.point_count_after = results.get('final_point_count')
            if results.get('operations'):
                total_time = sum(op.get('stats', {}).get('processing_time', 0) for op in results['operations'])
                job.processing_time = total_time
            db.commit()
        
        point_cloud = db.query(PointCloud).filter(PointCloud.id == point_cloud_id).first()
        if point_cloud:
            point_cloud.point_count = results.get('final_point_count')
            point_cloud.metadata = str(results.get('metadata', {}))
            db.commit()
        
        db.close()
        return results
        
    except PointCloudProcessingError as e:
        if job:
            job.status = ProcessingStatus.FAILED
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            db.commit()
        db.close()
        raise
    except Exception as e:
        if job:
            job.status = ProcessingStatus.FAILED
            job.error_message = f"Unexpected error: {str(e)}"
            job.updated_at = datetime.utcnow()
            db.commit()
        db.close()
        raise PointCloudProcessingError(f"Processing failed: {str(e)}")

@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_process: bool = Query(True, description="Whether to automatically process the uploaded file"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """上传点云文件"""
    validate_file(file)
    
    file_path, unique_filename, file_size = await save_upload_file(file, current_user.id)
    
    point_cloud = create_point_cloud_record(
        db=db,
        user_id=current_user.id,
        original_filename=file.filename,
        unique_filename=unique_filename,
        file_path=file_path,
        file_size=file_size
    )
    
    job_id = None
    if auto_process:
        output_dir = os.path.join(
            UPLOAD_DIR,
            f"user_{current_user.id}",
            f"processed_{point_cloud.id}"
        )
        os.makedirs(output_dir, exist_ok=True)
        
        job = ProcessingJob(
            job_id=task_manager.generate_task_id(),
            operation_type="full_processing",
            user_id=current_user.id,
            point_cloud_id=point_cloud.id,
            parameters='{"operations": ["statistical_outlier_removal", "voxel_downsample"]}'
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        job_id = job.job_id
        
        operations = [
            {'type': 'statistical_outlier_removal', 'parameters': {}},
            {'type': 'voxel_downsample', 'parameters': {'voxel_size': 0.01}}
        ]
        
        task_manager.submit_task(
            process_point_cloud_task,
            input_path=file_path,
            output_dir=output_dir,
            point_cloud_id=point_cloud.id,
            job_id=job_id,
            user_id=current_user.id,
            operations=operations,
            task_id=job_id
        )
        
        logger.info(f"File uploaded and processing started: job_id={job_id}, file_id={point_cloud.id}")
    
    return UploadResponse(
        message="File uploaded successfully" + (" and processing started" if auto_process else ""),
        file_id=point_cloud.id,
        filename=file.filename,
        file_size=file_size,
        job_id=job_id
    )

@router.get("/job/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取处理任务状态"""
    job = db.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    
    task_status = task_manager.get_task_status(job_id)
    
    if job.status == ProcessingStatus.PENDING and task_status.get('status') in ['running', 'completed', 'failed', 'timeout']:
        if task_status.get('status') == 'running':
            job.status = ProcessingStatus.PROCESSING
        elif task_status.get('status') == 'completed':
            job.status = ProcessingStatus.COMPLETED
        elif task_status.get('status') == 'failed':
            job.status = ProcessingStatus.FAILED
        elif task_status.get('status') == 'timeout':
            job.status = ProcessingStatus.TIMEOUT
        db.commit()
    
    return JobStatusResponse(
        job_id=job_id,
        status=job.status.value if isinstance(job.status, ProcessingStatus) else str(job.status),
        start_time=task_status.get('start_time'),
        duration=task_status.get('duration'),
        result=task_status.get('result'),
        error=task_status.get('error') or job.error_message
    )

@router.get("/files")
async def get_user_files(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    """获取用户上传的文件列表"""
    files = db.query(PointCloud)\
        .filter(PointCloud.user_id == current_user.id)\
        .order_by(PointCloud.created_at.desc())\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    total = db.query(PointCloud).filter(PointCloud.user_id == current_user.id).count()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "files": [
            {
                "id": f.id,
                "original_filename": f.original_filename,
                "file_size": f.file_size,
                "file_format": f.file_format,
                "point_count": f.point_count,
                "created_at": f.created_at.isoformat()
            } for f in files
        ]
    }

@router.get("/jobs")
async def get_user_jobs(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by job status")
):
    """获取用户的处理任务列表"""
    query = db.query(ProcessingJob).filter(ProcessingJob.user_id == current_user.id)
    
    if status:
        try:
            status_enum = ProcessingStatus(status.lower())
            query = query.filter(ProcessingJob.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status. Allowed values: {[s.value for s in ProcessingStatus]}")
    
    jobs = query.order_by(ProcessingJob.created_at.desc()).offset(skip).limit(limit).all()
    total = query.count()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status.value if isinstance(j.status, ProcessingStatus) else str(j.status),
                "operation_type": j.operation_type,
                "point_cloud_id": j.point_cloud_id,
                "processing_time": j.processing_time,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None
            } for j in jobs
        ]
    }
