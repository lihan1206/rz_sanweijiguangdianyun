from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.exceptions import (
    ErrorCode,
    PointCloudException,
    ProcessingException,
    raise_pointcloud_error,
    raise_processing_error,
)

logger = logging.getLogger(__name__)
settings = get_settings()

HAS_OPEN3D = False
HAS_LASPY = False

try:
    import open3d as o3d
    HAS_OPEN3D = True
except ImportError:
    logger.warning("Open3D 未安装，部分功能将受限")

try:
    import laspy
    HAS_LASPY = True
except ImportError:
    logger.warning("laspy 未安装，LAS 格式支持将受限")


SUPPORTED_FORMATS = {"las", "laz", "ply", "xyz", "csv"}
MAX_FILE_SIZE = settings.max_file_size_bytes
PROCESSING_TIMEOUT = settings.celery_task_timeout


class PointCloudService:
    def __init__(self, upload_dir: str | None = None):
        self.upload_dir = upload_dir or settings.upload_dir
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)

    def validate_file_format(self, filename: str) -> str:
        if not filename:
            raise_pointcloud_error(
                ErrorCode.FILE_FORMAT_UNSUPPORTED,
                "文件名不能为空",
            )
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix not in SUPPORTED_FORMATS:
            raise_pointcloud_error(
                ErrorCode.FILE_FORMAT_UNSUPPORTED,
                f"不支持的点云格式: {suffix}",
                {"supported_formats": list(SUPPORTED_FORMATS), "received_format": suffix},
            )
        return suffix

    def validate_file_size(self, file_size: int) -> None:
        if file_size > MAX_FILE_SIZE:
            raise_pointcloud_error(
                ErrorCode.FILE_TOO_LARGE,
                f"文件大小超过限制: {file_size / 1024 / 1024:.2f}MB > {MAX_FILE_SIZE / 1024 / 1024:.2f}MB",
                {
                    "max_size_mb": MAX_FILE_SIZE / 1024 / 1024,
                    "actual_size_mb": file_size / 1024 / 1024,
                },
            )

    def load_point_cloud(self, file_path: str, file_format: str) -> np.ndarray:
        logger.info("加载点云文件: %s (格式: %s)", file_path, file_format)

        if not os.path.exists(file_path):
            raise_pointcloud_error(
                ErrorCode.FILE_NOT_FOUND,
                f"文件不存在: {file_path}",
            )

        file_size = os.path.getsize(file_path)
        self.validate_file_size(file_size)

        try:
            if file_format in ("las", "laz"):
                return self._load_las(file_path)
            elif file_format == "ply":
                return self._load_ply(file_path)
            elif file_format in ("xyz", "csv"):
                return self._load_xyz(file_path)
            else:
                raise_pointcloud_error(
                    ErrorCode.FILE_FORMAT_UNSUPPORTED,
                    f"不支持的格式: {file_format}",
                )
        except PointCloudException:
            raise
        except MemoryError:
            raise_pointcloud_error(
                ErrorCode.PROCESSING_MEMORY_ERROR,
                "内存不足，无法加载点云文件",
                {"file_path": file_path, "file_size_mb": file_size / 1024 / 1024},
            )
        except Exception as e:
            raise_pointcloud_error(
                ErrorCode.FILE_PARSE_ERROR,
                f"加载点云文件失败: {str(e)}",
                {"file_path": file_path, "error": str(e)},
            )

    def _load_las(self, file_path: str) -> np.ndarray:
        if not HAS_LASPY:
            raise_pointcloud_error(
                ErrorCode.FILE_PARSE_ERROR,
                "laspy 未安装，无法加载 LAS 格式文件",
            )

        with laspy.open(file_path) as f:
            las = f.read()
            points = np.vstack((las.x, las.y, las.z)).transpose()

        logger.info("LAS 文件加载完成: %d 点", len(points))
        return points

    def _load_ply(self, file_path: str) -> np.ndarray:
        if HAS_OPEN3D:
            pcd = o3d.io.read_point_cloud(file_path)
            points = np.asarray(pcd.points)
        else:
            points = self._parse_ply_manually(file_path)

        logger.info("PLY 文件加载完成: %d 点", len(points))
        return points

    def _parse_ply_manually(self, file_path: str) -> np.ndarray:
        points: list[list[float]] = []
        header_ended = False
        vertex_count = 0

        with open(file_path, "rb") as f:
            for line in f:
                line_str = line.decode("utf-8", errors="ignore").strip()
                if line_str.lower() == "end_header":
                    header_ended = True
                    continue

                if not header_ended:
                    if line_str.lower().startswith("element vertex"):
                        parts = line_str.split()
                        if len(parts) >= 3:
                            vertex_count = int(parts[2])
                    continue

                if line_str and not line_str.startswith("comment"):
                    parts = line_str.split()
                    if len(parts) >= 3:
                        try:
                            points.append([float(parts[0]), float(parts[1]), float(parts[2])])
                        except ValueError:
                            continue

        return np.array(points, dtype=np.float64)

    def _load_xyz(self, file_path: str) -> np.ndarray:
        points: list[list[float]] = []

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        points.append([float(parts[0]), float(parts[1]), float(parts[2])])
                    except ValueError:
                        continue

        result = np.array(points, dtype=np.float64)
        logger.info("XYZ 文件加载完成: %d 点", len(result))
        return result

    def extract_metadata(self, file_path: str, file_format: str) -> dict[str, Any]:
        points = self.load_point_cloud(file_path, file_format)

        if len(points) == 0:
            return {
                "points_count": 0,
                "bounding_box": None,
                "centroid": None,
            }

        min_coords = points.min(axis=0)
        max_coords = points.max(axis=0)
        centroid = points.mean(axis=0)

        bounding_box = {
            "min_x": float(min_coords[0]),
            "min_y": float(min_coords[1]),
            "min_z": float(min_coords[2]),
            "max_x": float(max_coords[0]),
            "max_y": float(max_coords[1]),
            "max_z": float(max_coords[2]),
        }

        return {
            "points_count": len(points),
            "bounding_box": bounding_box,
            "centroid": centroid.tolist(),
        }

    def voxel_grid_filter(self, points: np.ndarray, voxel_size: float = 0.05) -> np.ndarray:
        logger.info("执行体素网格滤波: voxel_size=%.4f, 输入点数=%d", voxel_size, len(points))

        if len(points) == 0:
            return points

        if voxel_size <= 0:
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "体素大小必须大于0",
                {"voxel_size": voxel_size},
            )

        try:
            if HAS_OPEN3D:
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(points)
                downsampled = pcd.voxel_down_sample(voxel_size=voxel_size)
                result = np.asarray(downsampled.points)
            else:
                min_coords = points.min(axis=0)
                voxel_indices = np.floor((points - min_coords) / voxel_size).astype(int)
                _, unique_indices = np.unique(voxel_indices, axis=0, return_index=True)
                result = points[unique_indices]

            logger.info("体素网格滤波完成: %d -> %d 点", len(points), len(result))
            return result

        except MemoryError:
            raise_processing_error(
                ErrorCode.PROCESSING_MEMORY_ERROR,
                "内存不足，无法完成体素网格滤波",
            )

    def statistical_outlier_removal(
        self,
        points: np.ndarray,
        nb_neighbors: int = 20,
        std_ratio: float = 2.0,
    ) -> np.ndarray:
        logger.info(
            "执行统计离群点移除: nb_neighbors=%d, std_ratio=%.2f, 输入点数=%d",
            nb_neighbors,
            std_ratio,
            len(points),
        )

        if len(points) == 0:
            return points

        try:
            if HAS_OPEN3D:
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(points)
                cleaned, _ = pcd.remove_statistical_outlier(
                    nb_neighbors=nb_neighbors,
                    std_ratio=std_ratio,
                )
                result = np.asarray(cleaned.points)
            else:
                result = self._statistical_outlier_numpy(points, nb_neighbors, std_ratio)

            logger.info("统计离群点移除完成: %d -> %d 点", len(points), len(result))
            return result

        except MemoryError:
            raise_processing_error(
                ErrorCode.PROCESSING_MEMORY_ERROR,
                "内存不足，无法完成离群点移除",
            )

    def _statistical_outlier_numpy(
        self,
        points: np.ndarray,
        nb_neighbors: int,
        std_ratio: float,
    ) -> np.ndarray:
        n = len(points)
        if n < nb_neighbors:
            return points

        distances = np.zeros(n)
        for i in range(n):
            diff = points - points[i]
            dists = np.sqrt(np.sum(diff**2, axis=1))
            dists = np.sort(dists)
            distances[i] = np.mean(dists[1 : nb_neighbors + 1]) if n > nb_neighbors else np.mean(dists[1:])

        mean_dist = np.mean(distances)
        std_dist = np.std(distances)
        threshold = mean_dist + std_ratio * std_dist

        mask = distances < threshold
        return points[mask]

    def radius_outlier_removal(
        self,
        points: np.ndarray,
        radius: float = 1.0,
        min_neighbors: int = 5,
    ) -> np.ndarray:
        logger.info(
            "执行半径离群点移除: radius=%.4f, min_neighbors=%d, 输入点数=%d",
            radius,
            min_neighbors,
            len(points),
        )

        if len(points) == 0:
            return points

        try:
            if HAS_OPEN3D:
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(points)
                cleaned, _ = pcd.remove_radius_outlier(nb_points=min_neighbors, radius=radius)
                result = np.asarray(cleaned.points)
            else:
                result = self._radius_outlier_numpy(points, radius, min_neighbors)

            logger.info("半径离群点移除完成: %d -> %d 点", len(points), len(result))
            return result

        except MemoryError:
            raise_processing_error(
                ErrorCode.PROCESSING_MEMORY_ERROR,
                "内存不足，无法完成半径离群点移除",
            )

    def _radius_outlier_numpy(
        self,
        points: np.ndarray,
        radius: float,
        min_neighbors: int,
    ) -> np.ndarray:
        n = len(points)
        mask = np.ones(n, dtype=bool)

        for i in range(n):
            diff = points - points[i]
            dists = np.sqrt(np.sum(diff**2, axis=1))
            count = np.sum(dists < radius) - 1
            if count < min_neighbors:
                mask[i] = False

        return points[mask]

    def plane_segmentation(
        self,
        points: np.ndarray,
        distance_threshold: float = 0.01,
        ransac_n: int = 3,
        num_iterations: int = 1000,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        logger.info(
            "执行平面分割: distance_threshold=%.4f, 输入点数=%d",
            distance_threshold,
            len(points),
        )

        if len(points) < ransac_n:
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "点数不足，无法进行平面分割",
                {"points_count": len(points), "required": ransac_n},
            )

        try:
            if HAS_OPEN3D:
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(points)
                plane_model, inliers = pcd.segment_plane(
                    distance_threshold=distance_threshold,
                    ransac_n=ransac_n,
                    num_iterations=num_iterations,
                )

                inlier_points = points[inliers]
                outlier_points = np.delete(points, inliers, axis=0)

                plane_info = {
                    "plane_equation": {
                        "a": float(plane_model[0]),
                        "b": float(plane_model[1]),
                        "c": float(plane_model[2]),
                        "d": float(plane_model[3]),
                    },
                    "inlier_count": len(inlier_points),
                    "outlier_count": len(outlier_points),
                }
            else:
                inlier_points, outlier_points, plane_info = self._plane_segmentation_numpy(
                    points, distance_threshold, ransac_n, num_iterations
                )

            logger.info(
                "平面分割完成: 平面点=%d, 非平面点=%d",
                len(inlier_points),
                len(outlier_points),
            )
            return inlier_points, outlier_points, plane_info

        except MemoryError:
            raise_processing_error(
                ErrorCode.PROCESSING_MEMORY_ERROR,
                "内存不足，无法完成平面分割",
            )

    def _plane_segmentation_numpy(
        self,
        points: np.ndarray,
        distance_threshold: float,
        ransac_n: int,
        num_iterations: int,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        best_inliers = []
        best_plane = [0, 0, 1, 0]

        n = len(points)
        for _ in range(num_iterations):
            indices = np.random.choice(n, ransac_n, replace=False)
            sample = points[indices]

            v1 = sample[1] - sample[0]
            v2 = sample[2] - sample[0]
            normal = np.cross(v1, v2)
            norm = np.linalg.norm(normal)
            if norm < 1e-10:
                continue
            normal = normal / norm
            d = -np.dot(normal, sample[0])

            distances = np.abs(np.dot(points, normal) + d)
            inliers = np.where(distances < distance_threshold)[0]

            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_plane = [normal[0], normal[1], normal[2], d]

        inlier_points = points[best_inliers]
        outlier_points = np.delete(points, best_inliers, axis=0)

        plane_info = {
            "plane_equation": {
                "a": float(best_plane[0]),
                "b": float(best_plane[1]),
                "c": float(best_plane[2]),
                "d": float(best_plane[3]),
            },
            "inlier_count": len(inlier_points),
            "outlier_count": len(outlier_points),
        }

        return inlier_points, outlier_points, plane_info

    def icp_registration(
        self,
        source_points: np.ndarray,
        target_points: np.ndarray,
        threshold: float = 1.0,
        max_iteration: int = 100,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        logger.info(
            "执行ICP配准: 源点数=%d, 目标点数=%d, threshold=%.4f",
            len(source_points),
            len(target_points),
            threshold,
        )

        if len(source_points) == 0 or len(target_points) == 0:
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "源点云或目标点云为空",
            )

        try:
            if HAS_OPEN3D:
                source_pcd = o3d.geometry.PointCloud()
                source_pcd.points = o3d.utility.Vector3dVector(source_points)
                target_pcd = o3d.geometry.PointCloud()
                target_pcd.points = o3d.utility.Vector3dVector(target_points)

                reg_result = o3d.pipelines.registration.registration_icp(
                    source_pcd,
                    target_pcd,
                    threshold,
                    np.eye(4),
                    o3d.pipelines.registration.TransformationEstimationPointToPoint(),
                    o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=max_iteration),
                )

                transformed = source_pcd.transform(reg_result.transformation)
                transformed_points = np.asarray(transformed.points)

                registration_info = {
                    "fitness": float(reg_result.fitness),
                    "rmse": float(reg_result.inlier_rmse),
                    "transformation": reg_result.transformation.tolist(),
                }
            else:
                transformed_points, registration_info = self._icp_numpy(
                    source_points, target_points, threshold, max_iteration
                )

            logger.info("ICP配准完成: fitness=%.4f, rmse=%.4f", registration_info["fitness"], registration_info["rmse"])
            return transformed_points, registration_info

        except MemoryError:
            raise_processing_error(
                ErrorCode.PROCESSING_MEMORY_ERROR,
                "内存不足，无法完成ICP配准",
            )

    def _icp_numpy(
        self,
        source: np.ndarray,
        target: np.ndarray,
        threshold: float,
        max_iteration: int,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        transformation = np.eye(4)
        transformed = source.copy()

        for _ in range(max_iteration):
            indices = []
            for p in transformed:
                dists = np.sqrt(np.sum((target - p) ** 2, axis=1))
                nearest_idx = np.argmin(dists)
                if dists[nearest_idx] < threshold:
                    indices.append(nearest_idx)

            if len(indices) < 3:
                break

            corresponding_target = target[indices]
            centroid_source = transformed.mean(axis=0)
            centroid_target = corresponding_target.mean(axis=0)

            centered_source = transformed - centroid_source
            centered_target = corresponding_target - centroid_target

            h = centered_source.T @ centered_target
            u, _, vt = np.linalg.svd(h)
            r = vt.T @ u.T

            if np.linalg.det(r) < 0:
                vt[-1, :] *= -1
                r = vt.T @ u.T

            t = centroid_target - r @ centroid_source

            transformed = (r @ transformed.T).T + t

            temp_transform = np.eye(4)
            temp_transform[:3, :3] = r
            temp_transform[:3, 3] = t
            transformation = temp_transform @ transformation

        dists = np.sqrt(np.sum((target[np.array(indices)] - transformed[: len(indices)]) ** 2, axis=1))
        rmse = np.sqrt(np.mean(dists**2)) if len(dists) > 0 else float("inf")
        fitness = len(indices) / len(source)

        registration_info = {
            "fitness": float(fitness),
            "rmse": float(rmse),
            "transformation": transformation.tolist(),
        }

        return transformed, registration_info

    def save_point_cloud(
        self,
        points: np.ndarray,
        output_path: str,
        output_format: str = "ply",
    ) -> str:
        logger.info("保存点云文件: %s (格式: %s, 点数: %d)", output_path, output_format, len(points))

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if output_format == "ply":
                self._save_ply(points, str(output_path))
            elif output_format in ("las", "laz"):
                self._save_las(points, str(output_path), output_format)
            elif output_format == "xyz":
                self._save_xyz(points, str(output_path))
            else:
                raise_processing_error(
                    ErrorCode.FILE_FORMAT_UNSUPPORTED,
                    f"不支持的输出格式: {output_format}",
                )

            logger.info("点云文件保存成功: %s", output_path)
            return str(output_path)

        except Exception as e:
            raise_processing_error(
                ErrorCode.FILE_WRITE_ERROR,
                f"保存点云文件失败: {str(e)}",
                {"output_path": str(output_path), "error": str(e)},
            )

    def _save_ply(self, points: np.ndarray, file_path: str) -> None:
        if HAS_OPEN3D:
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            o3d.io.write_point_cloud(file_path, pcd)
        else:
            with open(file_path, "w") as f:
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"element vertex {len(points)}\n")
                f.write("property float x\n")
                f.write("property float y\n")
                f.write("property float z\n")
                f.write("end_header\n")
                for p in points:
                    f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")

    def _save_las(self, points: np.ndarray, file_path: str, output_format: str) -> None:
        if not HAS_LASPY:
            raise_processing_error(
                ErrorCode.FILE_WRITE_ERROR,
                "laspy 未安装，无法保存 LAS 格式文件",
            )

        header = laspy.LasHeader(point_format=3, version="1.2")
        header.x_scale = 0.0001
        header.y_scale = 0.0001
        header.z_scale = 0.0001
        header.x_offset = points[:, 0].min()
        header.y_offset = points[:, 1].min()
        header.z_offset = points[:, 2].min()

        las = laspy.LasData(header)
        las.x = points[:, 0]
        las.y = points[:, 1]
        las.z = points[:, 2]

        las.write(file_path)

    def _save_xyz(self, points: np.ndarray, file_path: str) -> None:
        with open(file_path, "w") as f:
            for p in points:
                f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")


point_cloud_service = PointCloudService()
