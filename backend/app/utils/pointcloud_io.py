from __future__ import annotations

import csv
import logging
import math
import os
import uuid
from pathlib import Path

import numpy as np
from fastapi import UploadFile, status

from app.core.exceptions import (
    ErrorCode,
    FileException,
    PointCloudException,
    raise_file_error,
    raise_pointcloud_error,
)

logger = logging.getLogger(__name__)

SUPPORTED_IMPORT_FORMATS = {"las", "laz", "ply", "xyz", "e57", "csv"}
PROCESSABLE_FORMATS = {"ply", "xyz", "csv"}

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
MAX_POINTS_IN_MEMORY = 50_000_000  # 5000万点


class FileValidationError(Exception):
    pass


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


def validate_file_size(file_size: int, max_size: int = MAX_FILE_SIZE) -> None:
    if file_size > max_size:
        raise_file_error(
            ErrorCode.FILE_TOO_LARGE,
            f"文件大小超过限制: {file_size / 1024 / 1024:.2f}MB > {max_size / 1024 / 1024:.2f}MB",
            {"max_size_mb": max_size / 1024 / 1024, "actual_size_mb": file_size / 1024 / 1024},
        )


def validate_file_format(filename: str | None) -> str:
    if not filename:
        raise_file_error(
            ErrorCode.FILE_FORMAT_UNSUPPORTED,
            "文件名不能为空",
        )
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_IMPORT_FORMATS:
        raise_file_error(
            ErrorCode.FILE_FORMAT_UNSUPPORTED,
            f"不支持的点云格式: {suffix}",
            {"supported_formats": list(SUPPORTED_IMPORT_FORMATS), "received_format": suffix},
        )
    return suffix


def validate_file_content(file_path: str, file_format: str) -> None:
    if not os.path.exists(file_path):
        raise_file_error(
            ErrorCode.FILE_NOT_FOUND,
            f"文件不存在: {file_path}",
        )

    if os.path.getsize(file_path) == 0:
        raise_file_error(
            ErrorCode.FILE_CORRUPTED,
            "文件为空",
            {"file_path": file_path},
        )

    if file_format == "ply":
        try:
            with open(file_path, "rb") as f:
                raw_header = f.readline()
                try:
                    header = raw_header.decode("utf-8").strip().lower()
                except UnicodeDecodeError:
                    header = raw_header.decode("latin-1").strip().lower()
                if not header.startswith("ply"):
                    raise_file_error(
                        ErrorCode.FILE_CORRUPTED,
                        "PLY文件头格式错误",
                        {"expected": "ply", "received": header[:10]},
                    )
        except UnicodeDecodeError:
            pass


def save_upload_file(upload_file: UploadFile, upload_dir: str) -> tuple[str, int, str]:
    suffix = validate_file_format(upload_file.filename)

    target_dir = Path(upload_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise_file_error(
            ErrorCode.FILE_WRITE_ERROR,
            f"无法创建上传目录: {str(e)}",
            {"upload_dir": upload_dir},
        )

    safe_name = f"{uuid.uuid4().hex}.{suffix}"
    target_path = target_dir / safe_name

    size = 0
    try:
        with target_path.open("wb") as f:
            while chunk := upload_file.file.read(1024 * 1024):
                size += len(chunk)
                validate_file_size(size)
                f.write(chunk)
    except FileException:
        if target_path.exists():
            target_path.unlink()
        raise
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        raise_file_error(
            ErrorCode.FILE_WRITE_ERROR,
            f"文件保存失败: {str(e)}",
            {"filename": upload_file.filename},
        )

    validate_file_content(str(target_path), suffix)

    return str(target_path), size, suffix


def _load_xyz_points(file_path: str) -> np.ndarray:
    points: list[list[float]] = []
    line_count = 0
    error_lines: list[int] = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                line_count += 1
                clean = line.strip()
                if not clean:
                    continue
                parts = clean.replace(",", " ").split()
                triplet = _parse_float_triplet(parts)
                if triplet:
                    points.append(triplet)
                elif line_num <= 100:
                    error_lines.append(line_num)

                if len(points) > MAX_POINTS_IN_MEMORY:
                    logger.warning("点云数据超过内存限制，截断处理")
                    break

    except FileNotFoundError:
        raise_file_error(
            ErrorCode.FILE_NOT_FOUND,
            f"文件不存在: {file_path}",
        )
    except Exception as e:
        raise_file_error(
            ErrorCode.FILE_PARSE_ERROR,
            f"解析XYZ文件失败: {str(e)}",
            {"file_path": file_path, "line_count": line_count},
        )

    if error_lines and len(error_lines) <= 10:
        logger.warning("XYZ文件解析警告，跳过无效行: %s", error_lines)

    if not points:
        raise_pointcloud_error(
            ErrorCode.POINTCLOUD_EMPTY,
            "XYZ文件不包含有效点数据",
            {"file_path": file_path, "total_lines": line_count},
        )

    return np.array(points, dtype=np.float64)


def _load_csv_points(file_path: str) -> np.ndarray:
    points: list[list[float]] = []
    row_count = 0
    error_rows: list[int] = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row_num, row in enumerate(reader, 1):
                row_count += 1
                triplet = _parse_float_triplet(row)
                if triplet:
                    points.append(triplet)
                elif row_num <= 100:
                    error_rows.append(row_num)

                if len(points) > MAX_POINTS_IN_MEMORY:
                    logger.warning("点云数据超过内存限制，截断处理")
                    break

    except FileNotFoundError:
        raise_file_error(
            ErrorCode.FILE_NOT_FOUND,
            f"文件不存在: {file_path}",
        )
    except Exception as e:
        raise_file_error(
            ErrorCode.FILE_PARSE_ERROR,
            f"解析CSV文件失败: {str(e)}",
            {"file_path": file_path, "row_count": row_count},
        )

    if error_rows and len(error_rows) <= 10:
        logger.warning("CSV文件解析警告，跳过无效行: %s", error_rows)

    if not points:
        raise_pointcloud_error(
            ErrorCode.POINTCLOUD_EMPTY,
            "CSV文件不包含有效点数据",
            {"file_path": file_path, "total_rows": row_count},
        )

    return np.array(points, dtype=np.float64)


def _load_ply_points(file_path: str) -> np.ndarray:
    points: list[list[float]] = []
    in_header = True
    vertex_count = 0
    actual_count = 0

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                clean = line.strip()

                if in_header:
                    if clean.startswith("element vertex"):
                        try:
                            vertex_count = int(clean.split()[-1])
                        except ValueError:
                            pass
                    if clean == "end_header":
                        in_header = False
                    continue

                if not clean:
                    continue

                parts = clean.split()
                triplet = _parse_float_triplet(parts)
                if triplet:
                    points.append(triplet)
                    actual_count += 1

                if len(points) > MAX_POINTS_IN_MEMORY:
                    logger.warning("点云数据超过内存限制，截断处理")
                    break

    except FileNotFoundError:
        raise_file_error(
            ErrorCode.FILE_NOT_FOUND,
            f"文件不存在: {file_path}",
        )
    except Exception as e:
        raise_file_error(
            ErrorCode.FILE_PARSE_ERROR,
            f"解析PLY文件失败: {str(e)}",
            {"file_path": file_path},
        )

    if vertex_count > 0 and actual_count < vertex_count * 0.9:
        logger.warning(
            "PLY文件点数不匹配: 声明 %d 点，实际解析 %d 点",
            vertex_count,
            actual_count,
        )

    if not points:
        raise_pointcloud_error(
            ErrorCode.POINTCLOUD_EMPTY,
            "PLY文件不包含有效点数据",
            {"file_path": file_path, "declared_vertices": vertex_count},
        )

    return np.array(points, dtype=np.float64)


def load_points(file_path: str, file_format: str) -> np.ndarray:
    fmt = file_format.lower()

    if not os.path.exists(file_path):
        raise_file_error(
            ErrorCode.FILE_NOT_FOUND,
            f"点云文件不存在: {file_path}",
        )

    if fmt == "xyz":
        return _load_xyz_points(file_path)
    if fmt == "csv":
        return _load_csv_points(file_path)
    if fmt == "ply":
        return _load_ply_points(file_path)

    raise_file_error(
        ErrorCode.FILE_FORMAT_UNSUPPORTED,
        f"当前仅支持对 xyz/csv/ply 执行处理，收到: {file_format}",
        {"supported_formats": list(PROCESSABLE_FORMATS), "received_format": file_format},
    )
    raise RuntimeError("unreachable")


def extract_metadata(file_path: str, file_format: str) -> tuple[int | None, dict | None]:
    if file_format.lower() not in PROCESSABLE_FORMATS:
        return None, None

    try:
        points = load_points(file_path, file_format)
    except (FileException, PointCloudException):
        logger.exception("提取元数据失败")
        return None, None

    if points.size == 0:
        return 0, {"x": [0, 0], "y": [0, 0], "z": [0, 0]}

    bbox = {
        "x": [float(points[:, 0].min()), float(points[:, 0].max())],
        "y": [float(points[:, 1].min()), float(points[:, 1].max())],
        "z": [float(points[:, 2].min()), float(points[:, 2].max())],
    }
    return int(points.shape[0]), bbox


def write_points(points: np.ndarray, output_path: str, fmt: str) -> None:
    if points.size == 0:
        raise_pointcloud_error(
            ErrorCode.POINTCLOUD_EMPTY,
            "无法写入空的点云数据",
            {"output_path": output_path},
        )

    target = Path(output_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise_file_error(
            ErrorCode.FILE_WRITE_ERROR,
            f"无法创建输出目录: {str(e)}",
            {"output_path": output_path},
        )

    try:
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

        raise_file_error(
            ErrorCode.FILE_FORMAT_UNSUPPORTED,
            f"不支持的导出格式: {fmt}",
            {"supported_formats": ["ply", "xyz", "csv"], "received_format": fmt},
        )

    except FileException:
        raise
    except Exception as e:
        raise_file_error(
            ErrorCode.FILE_WRITE_ERROR,
            f"写入文件失败: {str(e)}",
            {"output_path": output_path, "format": fmt},
        )


def estimate_density(points: np.ndarray) -> float:
    if points.size == 0:
        return 0.0
    dx = float(points[:, 0].max() - points[:, 0].min())
    dy = float(points[:, 1].max() - points[:, 1].min())
    area = max(dx * dy, 1e-6)
    return float(points.shape[0] / area)


def run_processing(points: np.ndarray, task_type: str, parameters: dict) -> np.ndarray:
    from app.core.exceptions import raise_processing_error

    if points.size == 0:
        raise_processing_error(
            ErrorCode.POINTCLOUD_EMPTY,
            "无法处理空的点云数据",
            {"task_type": task_type},
        )

    if task_type == "downsample":
        ratio = float(parameters.get("ratio", 0.5))
        if not 0 < ratio <= 1:
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "降采样比例必须在 (0, 1] 范围内",
                {"ratio": ratio, "valid_range": "(0, 1]"},
            )
        sample_size = max(1, int(points.shape[0] * ratio))
        indices = np.random.choice(points.shape[0], sample_size, replace=False)
        return points[indices]

    if task_type == "denoise":
        z = points[:, 2]
        mean = np.mean(z)
        std = np.std(z)
        if math.isclose(std, 0.0):
            logger.info("点云Z值标准差为0，跳过去噪")
            return points
        threshold = float(parameters.get("zscore", 2.0))
        if threshold <= 0:
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "Z-Score阈值必须大于0",
                {"zscore": threshold},
            )
        mask = np.abs((z - mean) / std) <= threshold
        result = points[mask]
        if result.size == 0:
            logger.warning("去噪后点云为空，返回原始数据")
            return points
        return result

    if task_type == "clip_z":
        min_z = float(parameters.get("min_z", np.min(points[:, 2])))
        max_z = float(parameters.get("max_z", np.max(points[:, 2])))
        if min_z > max_z:
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "最小Z值不能大于最大Z值",
                {"min_z": min_z, "max_z": max_z},
            )
        mask = (points[:, 2] >= min_z) & (points[:, 2] <= max_z)
        return points[mask]

    if task_type == "format_convert":
        return points

    raise_processing_error(
        ErrorCode.PROCESSING_INVALID_PARAMS,
        f"不支持的处理类型: {task_type}",
        {"supported_types": ["downsample", "denoise", "clip_z", "format_convert"]},
    )
    raise RuntimeError("unreachable")
