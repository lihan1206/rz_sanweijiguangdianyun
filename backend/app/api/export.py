from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.models.pointcloud import PointCloud
from app.models.user import User, UserRole
from app.utils.pointcloud_io import load_points, write_points

router = APIRouter(prefix="/export", tags=["导出功能"])
settings = get_settings()


@router.post("/{pointcloud_id}")
def export_pointcloud(
    pointcloud_id: int,
    export_format: str = "ply",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    导出生成下载链接
    支持格式: ply, obj, xyz, csv
    """
    record = db.query(PointCloud).filter(PointCloud.id == pointcloud_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="点云数据不存在")
    
    supported_formats = ["ply", "obj", "xyz", "csv"]
    if export_format not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出格式，支持: {', '.join(supported_formats)}"
        )
    
    # 加载点云数据
    points = load_points(record.storage_path, record.file_format)
    
    # 生成导出文件
    export_dir = Path(settings.upload_dir) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    export_filename = f"{record.name}_{uuid.uuid4().hex[:8]}.{export_format}"
    export_path = export_dir / export_filename
    
    if export_format == "obj":
        _write_obj(points, str(export_path))
    else:
        write_points(points, str(export_path), export_format)
    
    return {
        "download_url": f"/api/v1/export/download/{export_filename}",
        "filename": export_filename,
        "format": export_format,
        "points_count": len(points),
    }


@router.get("/download/{filename}")
def download_export(
    filename: str,
    _: User = Depends(get_current_user),
) -> FileResponse:
    """下载导出的文件"""
    export_dir = Path(settings.upload_dir) / "exports"
    file_path = export_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    
    return FileResponse(
        str(file_path),
        media_type="application/octet-stream",
        filename=filename,
    )


def _write_obj(points, output_path: str) -> None:
    """写入OBJ格式（仅支持点云）"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    
    with target.open("w", encoding="utf-8") as f:
        f.write("# Point cloud as OBJ vertices\n")
        for p in points:
            f.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
