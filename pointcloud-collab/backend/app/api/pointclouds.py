from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func
from typing import Optional, List
import os
import shutil
import uuid
import hashlib
from pathlib import Path
import aiofiles

from app.core.database import get_db
from app.core.security import get_current_user_id, upload_limiter
from app.core.config import settings
from app.models.point_cloud import PointCloud, PointCloudStatus, PointCloudVisibility, FileFormat
from app.models.file_chunk import FileChunk, ChunkStatus
from app.models.user import User
from app.utils.schemas import (
    ResponseBase, PointCloudCreate, PointCloudUpdate, PointCloudResponse,
    PointCloudListResponse, PointCloudFilterParams, UploadInitRequest, UploadInitResponse,
    MergeChunksRequest, ExportRequest, ExportResponse
)
from app.services.pointcloud_processor import processor

router = APIRouter(prefix="/pointclouds", tags=["Point Clouds"])

# 确保上传目录存在
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR = Path(settings.PROCESSED_DIR)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """检查文件类型是否允许"""
    ext = get_file_extension(filename)
    return ext in settings.ALLOWED_EXTENSIONS


def generate_file_hash(file_path: str) -> str:
    """生成文件MD5哈希"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


@router.post("/upload", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def upload_pointcloud(
    request: Request,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    scene_id: Optional[int] = Form(None),
    visibility: str = Form("private"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """上传点云文件"""
    # 限流检查
    client_ip = request.client.host
    if not upload_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Upload rate limit exceeded"
        )
    
    # 检查文件类型
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # 检查文件大小
    file.file.seek(0, 2)  # 移动到文件末尾
    file_size = file.file.tell()
    file.file.seek(0)  # 重置到开头
    
    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # 生成唯一文件名
    file_id = str(uuid.uuid4())
    ext = get_file_extension(file.filename)
    storage_filename = f"{file_id}{ext}"
    file_path = UPLOAD_DIR / storage_filename
    
    # 保存文件
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        file.file.close()
    
    # 计算文件哈希
    file_hash = generate_file_hash(str(file_path))
    
    # 解析点云获取信息
    try:
        pcd = processor.load_point_cloud(str(file_path))
        point_count = len(pcd.points)
        has_color = pcd.has_colors()
        has_normal = pcd.has_normals()
        bbox = processor.get_point_cloud_info(pcd)["bounding_box"]
    except Exception as e:
        # 解析失败，删除文件
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse point cloud: {str(e)}"
        )
    
    # 创建数据库记录
    point_cloud = PointCloud(
        user_id=user_id,
        scene_id=scene_id,
        name=name or file.filename,
        description=description,
        original_filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        file_format=FileFormat(ext[1:]),  # 去掉点号
        file_hash=file_hash,
        point_count=point_count,
        bounding_box=bbox,
        has_color=has_color,
        has_normal=has_normal,
        status=PointCloudStatus.READY,
        visibility=PointCloudVisibility(visibility)
    )
    
    db.add(point_cloud)
    await db.commit()
    await db.refresh(point_cloud)
    
    return ResponseBase(
        code=201,
        message="Point cloud uploaded successfully",
        data=point_cloud.to_dict(include_owner=True)
    )


@router.post("/upload/init", response_model=ResponseBase)
async def init_chunked_upload(
    request: UploadInitRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """初始化分片上传"""
    # 检查文件大小
    if request.file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # 检查文件类型
    if not is_allowed_file(request.file_name):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format"
        )
    
    upload_id = str(uuid.uuid4())
    total_chunks = (request.file_size + request.chunk_size - 1) // request.chunk_size
    
    return ResponseBase(
        code=200,
        data={
            "upload_id": upload_id,
            "total_chunks": total_chunks,
            "chunk_size": request.chunk_size
        }
    )


@router.post("/upload/chunk", response_model=ResponseBase)
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """上传分片"""
    # 保存分片
    chunk_dir = UPLOAD_DIR / "chunks" / upload_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / f"chunk_{chunk_index}"
    
    try:
        with open(chunk_path, "wb") as buffer:
            shutil.copyfileobj(chunk.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save chunk: {str(e)}"
        )
    finally:
        chunk.file.close()
    
    return ResponseBase(
        code=200,
        data={
            "chunk_index": chunk_index,
            "status": "uploaded"
        }
    )


@router.post("/upload/merge", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def merge_chunks(
    request: MergeChunksRequest,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    scene_id: Optional[int] = Form(None),
    visibility: str = Form("private"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """合并分片"""
    chunk_dir = UPLOAD_DIR / "chunks" / request.upload_id
    
    if not chunk_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )
    
    # 获取所有分片
    chunks = sorted(chunk_dir.glob("chunk_*"), key=lambda x: int(x.stem.split("_")[1]))
    
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chunks found"
        )
    
    # 合并文件
    file_id = str(uuid.uuid4())
    ext = ".ply"  # 默认格式，实际应从上传信息中获取
    storage_filename = f"{file_id}{ext}"
    file_path = UPLOAD_DIR / storage_filename
    
    try:
        with open(file_path, "wb") as outfile:
            for chunk_path in chunks:
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
        
        # 清理分片
        shutil.rmtree(chunk_dir)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to merge chunks: {str(e)}"
        )
    
    # 解析点云
    try:
        pcd = processor.load_point_cloud(str(file_path))
        point_count = len(pcd.points)
        has_color = pcd.has_colors()
        has_normal = pcd.has_normals()
        bbox = processor.get_point_cloud_info(pcd)["bounding_box"]
        file_size = os.path.getsize(file_path)
        file_hash = generate_file_hash(str(file_path))
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse point cloud: {str(e)}"
        )
    
    # 创建数据库记录
    point_cloud = PointCloud(
        user_id=user_id,
        scene_id=scene_id,
        name=name or f"pointcloud_{file_id}",
        description=description,
        original_filename=f"merged_{file_id}.ply",
        file_path=str(file_path),
        file_size=file_size,
        file_format=FileFormat.PLY,
        file_hash=file_hash,
        point_count=point_count,
        bounding_box=bbox,
        has_color=has_color,
        has_normal=has_normal,
        status=PointCloudStatus.READY,
        visibility=PointCloudVisibility(visibility)
    )
    
    db.add(point_cloud)
    await db.commit()
    await db.refresh(point_cloud)
    
    return ResponseBase(
        code=201,
        message="Point cloud uploaded successfully",
        data=point_cloud.to_dict(include_owner=True)
    )


@router.get("", response_model=ResponseBase)
async def list_pointclouds(
    params: PointCloudFilterParams = Depends(),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取点云列表"""
    # 构建查询
    query = select(PointCloud).where(
        or_(
            PointCloud.user_id == user_id,
            PointCloud.visibility == PointCloudVisibility.PUBLIC,
            and_(
                PointCloud.scene_id.isnot(None),
                PointCloud.visibility == PointCloudVisibility.SCENE_ONLY
            )
        )
    )
    
    # 应用过滤条件
    if params.status:
        query = query.where(PointCloud.status == params.status)
    if params.scene_id:
        query = query.where(PointCloud.scene_id == params.scene_id)
    if params.search:
        search_filter = or_(
            PointCloud.name.ilike(f"%{params.search}%"),
            PointCloud.description.ilike(f"%{params.search}%")
        )
        query = query.where(search_filter)
    
    # 排序
    sort_column = getattr(PointCloud, params.sort_by, PointCloud.created_at)
    if params.sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # 分页
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()
    
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    
    result = await db.execute(query)
    point_clouds = result.scalars().all()
    
    return ResponseBase(
        code=200,
        data={
            "items": [pc.to_dict(include_owner=True) for pc in point_clouds],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "pages": (total + params.page_size - 1) // params.page_size
        }
    )


@router.get("/{pointcloud_id}", response_model=ResponseBase)
async def get_pointcloud(
    pointcloud_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取点云详情"""
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == pointcloud_id)
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
    
    return ResponseBase(
        code=200,
        data=point_cloud.to_dict(include_owner=True)
    )


@router.get("/{pointcloud_id}/data")
async def get_pointcloud_data(
    pointcloud_id: int,
    format: str = "json",
    max_points: int = Query(1000000, ge=1000, le=10000000),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取点云数据（用于可视化）"""
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == pointcloud_id)
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
    
    # 检查文件是否存在
    if not os.path.exists(point_cloud.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Point cloud file not found"
        )
    
    # 加载并转换点云
    try:
        pcd = processor.load_point_cloud(point_cloud.file_path)
        data = processor.convert_to_binary_data(pcd, max_points)
        
        if format == "bin":
            # 返回二进制流
            return StreamingResponse(
                iter([data["points"]]),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename=pointcloud_{pointcloud_id}.bin"}
            )
        else:
            # 返回JSON格式
            return ResponseBase(
                code=200,
                data={
                    "format": "json",
                    "point_count": data["point_count"],
                    "has_color": data["has_color"],
                    "has_normal": data["has_normal"],
                    "bounding_box": data["bounding_box"],
                    "points_url": f"/api/v1/pointclouds/{pointcloud_id}/points.bin",
                    "colors_url": f"/api/v1/pointclouds/{pointcloud_id}/colors.bin" if data["has_color"] else None,
                }
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load point cloud: {str(e)}"
        )


@router.get("/{pointcloud_id}/points.bin")
async def get_pointcloud_points(
    pointcloud_id: int,
    max_points: int = Query(1000000, ge=1000, le=10000000),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取点云坐标二进制数据"""
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == pointcloud_id)
    )
    point_cloud = result.scalar_one_or_none()
    
    if not point_cloud:
        raise HTTPException(status_code=404, detail="Point cloud not found")
    
    if point_cloud.user_id != user_id and point_cloud.visibility == PointCloudVisibility.PRIVATE:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        pcd = processor.load_point_cloud(point_cloud.file_path)
        data = processor.convert_to_binary_data(pcd, max_points)
        
        return StreamingResponse(
            iter([data["points"]]),
            media_type="application/octet-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pointcloud_id}/colors.bin")
async def get_pointcloud_colors(
    pointcloud_id: int,
    max_points: int = Query(1000000, ge=1000, le=10000000),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取点云颜色二进制数据"""
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == pointcloud_id)
    )
    point_cloud = result.scalar_one_or_none()
    
    if not point_cloud:
        raise HTTPException(status_code=404, detail="Point cloud not found")
    
    if point_cloud.user_id != user_id and point_cloud.visibility == PointCloudVisibility.PRIVATE:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        pcd = processor.load_point_cloud(point_cloud.file_path)
        if not pcd.has_colors():
            raise HTTPException(status_code=404, detail="No color data")
        
        data = processor.convert_to_binary_data(pcd, max_points)
        
        return StreamingResponse(
            iter([data["colors"]]),
            media_type="application/octet-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{pointcloud_id}", response_model=ResponseBase)
async def update_pointcloud(
    pointcloud_id: int,
    update_data: PointCloudUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """更新点云信息"""
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == pointcloud_id)
    )
    point_cloud = result.scalar_one_or_none()
    
    if not point_cloud:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Point cloud not found"
        )
    
    # 检查权限
    if point_cloud.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # 更新字段
    if update_data.name is not None:
        point_cloud.name = update_data.name
    if update_data.description is not None:
        point_cloud.description = update_data.description
    if update_data.visibility is not None:
        point_cloud.visibility = update_data.visibility
    
    await db.commit()
    await db.refresh(point_cloud)
    
    return ResponseBase(
        code=200,
        message="Point cloud updated",
        data=point_cloud.to_dict(include_owner=True)
    )


@router.delete("/{pointcloud_id}", response_model=ResponseBase)
async def delete_pointcloud(
    pointcloud_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """删除点云"""
    result = await db.execute(
        select(PointCloud).where(PointCloud.id == pointcloud_id)
    )
    point_cloud = result.scalar_one_or_none()
    
    if not point_cloud:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Point cloud not found"
        )
    
    # 检查权限
    if point_cloud.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # 删除文件
    try:
        if os.path.exists(point_cloud.file_path):
            os.remove(point_cloud.file_path)
    except Exception:
        pass  # 文件可能已被删除
    
    # 软删除（更新状态）
    point_cloud.status = PointCloudStatus.DELETED
    await db.commit()
    
    return ResponseBase(
        code=200,
        message="Point cloud deleted"
    )


@router.post("/{pointcloud_id}/export", response_model=ResponseBase, status_code=status.HTTP_202_ACCEPTED)
async def export_pointcloud(
    pointcloud_id: int,
    export_request: ExportRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """导出点云（创建异步任务）"""
    # TODO: 实现导出任务队列
    return ResponseBase(
        code=202,
        message="Export task created",
        data={
            "task_id": 0,
            "status": "queued",
            "download_url": None
        }
    )
