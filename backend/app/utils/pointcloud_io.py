from __future__ import annotations

import csv
import math
import uuid
from pathlib import Path

import numpy as np
from fastapi import HTTPException, UploadFile, status

SUPPORTED_IMPORT_FORMATS = {"las", "laz", "ply", "xyz", "e57", "csv"}
PROCESSABLE_FORMATS = {"ply", "xyz", "csv"}


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


def save_upload_file(upload_file: UploadFile, upload_dir: str) -> tuple[str, int, str]:
    suffix = Path(upload_file.filename or "").suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_IMPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的点云格式: {suffix}，当前支持 {', '.join(sorted(SUPPORTED_IMPORT_FORMATS))}",
        )

    target_dir = Path(upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

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

    raise HTTPException(status_code=400, detail=f"不支持的处理类型: {task_type}")
