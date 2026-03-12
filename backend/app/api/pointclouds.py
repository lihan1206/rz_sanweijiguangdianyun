from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.models.pointcloud import PointCloud
from app.models.user import User, UserRole
from app.schemas.pointcloud import (
    DeleteResponse,
    PointCloudDetail,
    PointCloudListItem,
    PointCloudStats,
    PointSample,
    RestoreResponse,
    UploadResponse,
)
from app.services.audit import write_audit_log
from app.utils.pointcloud_io import (
    estimate_density,
    extract_metadata,
    load_points,
    parse_tags,
    save_upload_file,
)

router = APIRouter(prefix="/pointclouds", tags=["点云管理"])
settings = get_settings()


@router.get("", response_model=list[PointCloudListItem])
def list_pointclouds(
    include_deleted: bool = Query(default=False),
    group_name: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PointCloudListItem]:
    query = db.query(PointCloud)
    if not include_deleted:
        query = query.filter(PointCloud.is_deleted.is_(False))
    if group_name:
        query = query.filter(PointCloud.group_name == group_name)
    if keyword:
        query = query.filter(PointCloud.name.contains(keyword))

    records = query.order_by(PointCloud.created_at.desc()).all()
    return [PointCloudListItem.model_validate(item) for item in records]


@router.get("/{pointcloud_id}", response_model=PointCloudDetail)
def get_pointcloud(
    pointcloud_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PointCloudDetail:
    record = db.query(PointCloud).filter(PointCloud.id == pointcloud_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="点云数据不存在")
    return PointCloudDetail.model_validate(record)


@router.post("/upload", response_model=UploadResponse)
def upload_pointcloud(
    file: UploadFile = File(...),
    name: str = Form(...),
    group_name: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    capture_time: str | None = Form(default=None),
    sensor_model: str | None = Form(default=None),
    coordinate_system: str | None = Form(default=None),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> UploadResponse:
    storage_path, file_size, file_format = save_upload_file(file, settings.upload_dir)
    points_count, bbox = extract_metadata(storage_path, file_format)

    parsed_capture_time = None
    if capture_time:
        try:
            parsed_capture_time = datetime.fromisoformat(capture_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="采集时间格式错误，请使用 ISO 时间") from exc

    record = PointCloud(
        name=name,
        original_filename=file.filename or "未知文件",
        storage_path=storage_path,
        file_format=file_format,
        file_size=file_size,
        points_count=points_count,
        capture_time=parsed_capture_time,
        sensor_model=sensor_model,
        coordinate_system=coordinate_system,
        bounding_box=bbox,
        group_name=group_name,
        tags=parse_tags(tags),
        created_by=current_user.id,
    )
    db.add(record)
    db.flush()

    write_audit_log(
        db,
        action="上传点云",
        target_type="pointcloud",
        target_id=str(record.id),
        user_id=current_user.id,
        detail={"name": name, "format": file_format},
    )

    db.commit()
    return UploadResponse(id=record.id, message="上传成功")


@router.delete("/{pointcloud_id}", response_model=DeleteResponse)
def soft_delete_pointcloud(
    pointcloud_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    record = db.query(PointCloud).filter(PointCloud.id == pointcloud_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="点云数据不存在")

    record.is_deleted = True
    record.deleted_at = datetime.utcnow()

    write_audit_log(
        db,
        action="删除点云(软删除)",
        target_type="pointcloud",
        target_id=str(record.id),
        user_id=current_user.id,
        detail={"name": record.name},
    )

    db.commit()
    return DeleteResponse(message="删除成功，可在回收站恢复")


@router.post("/{pointcloud_id}/restore", response_model=RestoreResponse)
def restore_pointcloud(
    pointcloud_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> RestoreResponse:
    record = db.query(PointCloud).filter(PointCloud.id == pointcloud_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="点云数据不存在")

    record.is_deleted = False
    record.deleted_at = None

    write_audit_log(
        db,
        action="恢复点云",
        target_type="pointcloud",
        target_id=str(record.id),
        user_id=current_user.id,
    )

    db.commit()
    return RestoreResponse(message="恢复成功")


@router.get("/{pointcloud_id}/stats", response_model=PointCloudStats)
def pointcloud_stats(
    pointcloud_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PointCloudStats:
    record = db.query(PointCloud).filter(PointCloud.id == pointcloud_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="点云数据不存在")

    points = load_points(record.storage_path, record.file_format)
    if points.size == 0:
        return PointCloudStats(
            total_points=0,
            density_estimate=0,
            x_range=(0, 0),
            y_range=(0, 0),
            z_range=(0, 0),
        )

    return PointCloudStats(
        total_points=int(points.shape[0]),
        density_estimate=estimate_density(points),
        x_range=(float(points[:, 0].min()), float(points[:, 0].max())),
        y_range=(float(points[:, 1].min()), float(points[:, 1].max())),
        z_range=(float(points[:, 2].min()), float(points[:, 2].max())),
    )


@router.get("/{pointcloud_id}/sample", response_model=PointSample)
def pointcloud_sample(
    pointcloud_id: int,
    limit: int = Query(default=1000, ge=100, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PointSample:
    record = db.query(PointCloud).filter(PointCloud.id == pointcloud_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="点云数据不存在")

    points = load_points(record.storage_path, record.file_format)
    if points.shape[0] > limit:
        points = points[:limit]
    return PointSample(points=points.tolist())
