from __future__ import annotations

import csv
import hashlib
import math
import re
import uuid
from pathlib import Path
from typing import BinaryIO, Tuple

import numpy as np
from fastapi import HTTPException, UploadFile, status

SUPPORTED_IMPORT_FORMATS = {"las", "laz", "ply", "xyz", "e57", "csv", "pcd"}
PROCESSABLE_FORMATS = {"ply", "xyz", "csv"}
MESH_OUTPUT_FORMATS = {"ply", "obj", "stl"}

# 安全配置
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
ALLOWED_MIME_TYPES = {
    "application/octet-stream",
    "text/plain",
    "text/csv",
    "application/ply",
    "application/vnd.las",
}
# 危险的文件头特征 (防止恶意文件上传)
DANGEROUS_PATTERNS = [
    b"<?php",
    b"<script",
    b"#!/bin/bash",
    b"#!/usr/bin/env",
    b"CMD",
    b"RUN ",
]
# PLY文件头正则匹配 (用于验证PLY文件格式)
PLY_HEADER_PATTERN = re.compile(rb"^ply\nformat (ascii|binary_little_endian|binary_big_endian) 1.0\n")


def _parse_float_triplet(parts: list[str]) -> list[float] | None:
    if len(parts) < 3:
        return None
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except ValueError:
        return None


def parse_tags(raw_tags: str | None) -> list[str]:
    if not raw_tags:
        return []
    tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
    return list(dict.fromkeys(tags))


def validate_file_content(file_obj: BinaryIO, suffix: str) -> None:
    """
    验证文件内容是否为合法的点云文件，防止恶意文件上传
    """
    # 读取文件头进行检查
    header = file_obj.read(4096)
    file_obj.seek(0)  # 重置文件指针

    # 检查危险模式
    for pattern in DANGEROUS_PATTERNS:
        if pattern in header.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件包含恶意内容，上传被拒绝",
            )

    # 按格式验证文件内容
    if suffix == "ply":
        # 验证PLY文件头
        if not PLY_HEADER_PATTERN.match(header):
            # 尝试检查二进制格式
            if not header.startswith(b"ply"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的PLY文件格式",
                )
    elif suffix in ["xyz", "csv"]:
        # 检查文本文件是否包含有效的数值数据
        lines = header.split(b"\n")[:10]
        valid_lines = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith(b"#"):
                continue
            # 尝试解析为浮点数三元组
            parts = line.replace(b",", b" ").split()
            if len(parts) >= 3:
                try:
                    float(parts[0]), float(parts[1]), float(parts[2])
                    valid_lines += 1
                except ValueError:
                    continue
        if valid_lines == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件内容无效，无法解析为点云数据",
            )


def save_upload_file(upload_file: UploadFile, upload_dir: str) -> tuple[str, int, str]:
    suffix = Path(upload_file.filename or "").suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_IMPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的点云格式: {suffix}，当前支持 {', '.join(sorted(SUPPORTED_IMPORT_FORMATS))}",
        )

    # 检查文件大小
    upload_file.file.seek(0, 2)  # 移动到文件末尾
    file_size = upload_file.file.tell()
    upload_file.file.seek(0)  # 重置文件指针

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件过大 ({file_size / 1024 / 1024:.2f} MB)，最大支持 {MAX_FILE_SIZE / 1024 / 1024} MB",
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传文件为空",
        )

    # 验证文件内容
    validate_file_content(upload_file.file, suffix)

    target_dir = Path(upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 使用安全的文件名
    safe_name = f"{uuid.uuid4().hex}.{suffix}"
    target_path = target_dir / safe_name

    size = 0
    with target_path.open("wb") as f:
        while chunk := upload_file.file.read(1024 * 1024):
            size += len(chunk)
            f.write(chunk)

    return str(target_path), size, suffix


def _load_xyz_points(file_path: str) -> np.ndarray:
    points: list[list[float]] = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean = line.strip()
            if not clean:
                continue
            parts = clean.replace(",", " ").split()
            triplet = _parse_float_triplet(parts)
            if triplet:
                points.append(triplet)
    return np.array(points, dtype=np.float64) if points else np.empty((0, 3))


def _load_csv_points(file_path: str) -> np.ndarray:
    points: list[list[float]] = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            triplet = _parse_float_triplet(row)
            if triplet:
                points.append(triplet)
    return np.array(points, dtype=np.float64) if points else np.empty((0, 3))


def _load_ply_points(file_path: str) -> np.ndarray:
    points: list[list[float]] = []
    in_header = True
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean = line.strip()
            if in_header:
                if clean == "end_header":
                    in_header = False
                continue
            if not clean:
                continue
            parts = clean.split()
            triplet = _parse_float_triplet(parts)
            if triplet:
                points.append(triplet)
    return np.array(points, dtype=np.float64) if points else np.empty((0, 3))


def load_points(file_path: str, file_format: str) -> np.ndarray:
    fmt = file_format.lower()
    if fmt == "xyz":
        return _load_xyz_points(file_path)
    if fmt == "csv":
        return _load_csv_points(file_path)
    if fmt == "ply":
        return _load_ply_points(file_path)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"当前仅支持对 xyz/csv/ply 执行处理，收到: {file_format}",
    )


def extract_metadata(file_path: str, file_format: str) -> tuple[int | None, dict | None]:
    if file_format.lower() not in PROCESSABLE_FORMATS:
        return None, None

    points = load_points(file_path, file_format)
    if points.size == 0:
        return 0, {"x": [0, 0], "y": [0, 0], "z": [0, 0]}

    bbox = {
        "x": [float(points[:, 0].min()), float(points[:, 0].max())],
        "y": [float(points[:, 1].min()), float(points[:, 1].max())],
        "z": [float(points[:, 2].min()), float(points[:, 2].max())],
    }
    return int(points.shape[0]), bbox


def write_points(points: np.ndarray, output_path: str, fmt: str) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "xyz":
        with target.open("w", encoding="utf-8") as f:
            for p in points:
                f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
        return

    if fmt == "csv":
        with target.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            for p in points:
                writer.writerow([f"{p[0]:.6f}", f"{p[1]:.6f}", f"{p[2]:.6f}"])
        return

    if fmt == "ply":
        with target.open("w", encoding="utf-8") as f:
            f.write("ply\n")
            f.write("format ascii 1.0\n")
            f.write(f"element vertex {len(points)}\n")
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write("end_header\n")
            for p in points:
                f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
        return

    raise HTTPException(status_code=400, detail=f"不支持的导出格式: {fmt}")


def write_mesh_data(vertices: np.ndarray, faces: np.ndarray, output_path: str, fmt: str) -> None:
    """写入网格数据"""
    from app.utils.pointcloud_processing import write_mesh as _write_mesh
    success = _write_mesh(vertices, faces, output_path, fmt)
    if not success:
        raise HTTPException(status_code=500, detail="网格写入失败")


def estimate_density(points: np.ndarray) -> float:
    if points.size == 0:
        return 0.0
    dx = float(points[:, 0].max() - points[:, 0].min())
    dy = float(points[:, 1].max() - points[:, 1].min())
    area = max(dx * dy, 1e-6)
    return float(points.shape[0] / area)


def run_processing(points: np.ndarray, task_type: str, parameters: dict) -> np.ndarray:
    if points.size == 0:
        return points

    if task_type == "downsample":
        ratio = float(parameters.get("ratio", 0.5))
        ratio = min(max(ratio, 0.01), 1.0)
        sample_size = max(1, int(points.shape[0] * ratio))
        indices = np.random.choice(points.shape[0], sample_size, replace=False)
        return points[indices]

    if task_type == "denoise":
        z = points[:, 2]
        mean = np.mean(z)
        std = np.std(z)
        if math.isclose(std, 0.0):
            return points
        threshold = float(parameters.get("zscore", 2.0))
        mask = np.abs((z - mean) / std) <= threshold
        return points[mask]

    if task_type == "clip_z":
        min_z = float(parameters.get("min_z", np.min(points[:, 2])))
        max_z = float(parameters.get("max_z", np.max(points[:, 2])))
        mask = (points[:, 2] >= min_z) & (points[:, 2] <= max_z)
        return points[mask]

    if task_type == "format_convert":
        return points

    # 新算法：体素格滤波
    if task_type == "voxel_grid":
        voxel_size = float(parameters.get("voxel_size", 0.05))
        from app.utils.pointcloud_processing import voxel_grid_filter
        return voxel_grid_filter(points, voxel_size)

    # 新算法：统计离群点移除
    if task_type == "statistical_outlier":
        nb_neighbors = int(parameters.get("nb_neighbors", 20))
        std_ratio = float(parameters.get("std_ratio", 2.0))
        from app.utils.pointcloud_processing import statistical_outlier_removal
        return statistical_outlier_removal(points, nb_neighbors, std_ratio)

    # 新算法：RANSAC平面分割
    if task_type == "ransac_plane":
        distance_threshold = float(parameters.get("distance_threshold", 0.01))
        ransac_n = int(parameters.get("ransac_n", 3))
        num_iterations = int(parameters.get("num_iterations", 1000))
        keep_inliers = parameters.get("keep_inliers", True)
        from app.utils.pointcloud_processing import ransac_plane_segmentation
        inliers, outliers, _ = ransac_plane_segmentation(
            points, distance_threshold, ransac_n, num_iterations, return_plane=True
        )
        return inliers if keep_inliers else outliers

    # 新算法：直通滤波
    if task_type == "passthrough":
        axis = parameters.get("axis", "z")
        min_val = parameters.get("min_val")
        max_val = parameters.get("max_val")
        if min_val is not None:
            min_val = float(min_val)
        if max_val is not None:
            max_val = float(max_val)
        from app.utils.pointcloud_processing import passthrough_filter
        return passthrough_filter(points, axis, min_val, max_val)

    # 体素化
    if task_type == "voxelization":
        voxel_size = float(parameters.get("voxel_size", 0.1))
        from app.utils.pointcloud_processing import voxelization
        voxel_centers, _ = voxelization(points, voxel_size)
        return voxel_centers
    
    # Poisson 表面重建（网格化）
    if task_type == "poisson_reconstruction":
        depth = int(parameters.get("depth", 8))
        min_density = float(parameters.get("min_density", 0.01))
        from app.utils.pointcloud_processing import poisson_surface_reconstruction
        vertices, faces = poisson_surface_reconstruction(points, depth, min_density)
        # 返回顶点和面片信息，这里我们返回顶点用于点云显示
        return vertices
    
    # 网格化
    if task_type == "meshing":
        voxel_size = float(parameters.get("voxel_size", 0.1))
        from app.utils.pointcloud_processing import marching_cubes_reconstruction
        vertices, faces = marching_cubes_reconstruction(points, voxel_size)
        return vertices

    raise HTTPException(status_code=400, detail=f"不支持的处理类型: {task_type}")


def calculate_file_hash(file_path: str, hash_algorithm: str = "md5") -> str:
    """
    计算文件哈希值用于完整性校验
    :param file_path: 文件路径
    :param hash_algorithm: 哈希算法 (md5, sha1, sha256)
    :return: 哈希值字符串
    """
    hash_func = {
        "md5": hashlib.md5(),
        "sha1": hashlib.sha1(),
        "sha256": hashlib.sha256(),
    }.get(hash_algorithm.lower(), hashlib.md5())
    
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def verify_file_integrity(file_path: str, expected_hash: str, hash_algorithm: str = "md5") -> bool:
    """
    验证文件完整性
    :param file_path: 文件路径
    :param expected_hash: 预期的哈希值
    :param hash_algorithm: 哈希算法
    :return: 是否验证通过
    """
    if not Path(file_path).exists():
        return False
    
    actual_hash = calculate_file_hash(file_path, hash_algorithm)
    return actual_hash.lower() == expected_hash.lower()
