from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.pointcloud import PointCloud
from app.models.user import User, UserRole
from app.utils.pointcloud_io import extract_metadata, write_points

logger = logging.getLogger(__name__)


def seed_data(db: Session, upload_dir: str) -> None:
    _seed_users(db)
    _seed_demo_pointcloud(db, upload_dir)


def _seed_users(db: Session) -> None:
    if db.query(User).count() > 0:
        return

    users = [
        User(username="admin", password_hash=get_password_hash("123456"), role=UserRole.ADMIN),
        User(username="engineer", password_hash=get_password_hash("123456"), role=UserRole.ENGINEER),
        User(username="viewer", password_hash=get_password_hash("123456"), role=UserRole.VIEWER),
    ]
    db.add_all(users)
    db.commit()
    logger.info("初始化用户完成，创建 3 个默认账号")


def _seed_demo_pointcloud(db: Session, upload_dir: str) -> None:
    exists = db.query(PointCloud).filter(PointCloud.name == "演示点云数据").first()
    if exists:
        return

    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        return

    path = Path(upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / "demo_points.xyz"

    x = np.linspace(-10, 10, 30)
    y = np.linspace(-10, 10, 30)
    xx, yy = np.meshgrid(x, y)
    zz = np.sin(xx / 3) + np.cos(yy / 4)
    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    write_points(points, str(file_path), "xyz")

    points_count, bbox = extract_metadata(str(file_path), "xyz")

    record = PointCloud(
        name="演示点云数据",
        original_filename="demo_points.xyz",
        storage_path=str(file_path),
        file_format="xyz",
        file_size=file_path.stat().st_size,
        points_count=points_count,
        bounding_box=bbox,
        group_name="默认项目",
        tags=["演示", "地形"],
        version=1,
        created_by=admin.id,
    )
    db.add(record)
    db.commit()
    logger.info("初始化演示点云完成")
