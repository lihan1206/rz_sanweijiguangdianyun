from __future__ import annotations

import logging
import math
import signal
import traceback
from contextlib import contextmanager
from typing import Any, Generator

import numpy as np

from app.core.exceptions import (
    ErrorCode,
    ProcessingException,
    raise_processing_error,
)

logger = logging.getLogger(__name__)

HAS_OPEN3D = False
try:
    import open3d as o3d
    HAS_OPEN3D = True
except ImportError:
    logger.warning("Open3D 未安装，高级处理功能将使用 NumPy 实现")

DEFAULT_TIMEOUT_SECONDS = 1800  # 30分钟
MAX_POINTS_FOR_PROCESSING = 100_000_000  # 1亿点


class TimeoutError(Exception):
    pass


@contextmanager
def timeout_handler(seconds: int) -> Generator[None, None, None]:
    def handler(signum, frame):
        raise TimeoutError(f"处理超时: 超过 {seconds} 秒")

    original_handler = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)


def validate_points(points: np.ndarray, operation: str) -> None:
    if points.size == 0:
        raise_processing_error(
            ErrorCode.POINTCLOUD_EMPTY,
            f"{operation}: 点云数据为空",
            {"operation": operation},
        )

    if len(points.shape) != 2 or points.shape[1] < 3:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            f"{operation}: 点云数据格式错误，期望 N×3 数组",
            {"operation": operation, "shape": points.shape},
        )

    if len(points) > MAX_POINTS_FOR_PROCESSING:
        logger.warning(
            "点云数量超过建议上限: %d > %d，处理可能较慢",
            len(points),
            MAX_POINTS_FOR_PROCESSING,
        )


def validate_voxel_size(voxel_size: float) -> None:
    if voxel_size <= 0:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "体素大小必须大于0",
            {"voxel_size": voxel_size},
        )
    if voxel_size > 1000:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "体素大小过大，可能导致数据丢失",
            {"voxel_size": voxel_size, "max_recommended": 1000},
        )


def validate_neighbors(nb_neighbors: int) -> None:
    if nb_neighbors < 1:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "邻居数量必须至少为1",
            {"nb_neighbors": nb_neighbors},
        )
    if nb_neighbors > 1000:
        logger.warning("邻居数量设置过大: %d，可能影响性能", nb_neighbors)


def validate_std_ratio(std_ratio: float) -> None:
    if std_ratio <= 0:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "标准差比率必须大于0",
            {"std_ratio": std_ratio},
        )


def validate_distance_threshold(threshold: float, operation: str) -> None:
    if threshold <= 0:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            f"{operation}: 距离阈值必须大于0",
            {"distance_threshold": threshold, "operation": operation},
        )


def voxel_grid_filter(points: np.ndarray, voxel_size: float = 0.05) -> np.ndarray:
    validate_points(points, "体素网格滤波")
    validate_voxel_size(voxel_size)

    try:
        if HAS_OPEN3D:
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            downsampled = pcd.voxel_down_sample(voxel_size=voxel_size)
            result = np.asarray(downsampled.points)
            logger.info(
                "体素网格滤波完成: %d -> %d 点 (体素大小: %.4f)",
                len(points),
                len(result),
                voxel_size,
            )
            return result

        min_coords = points.min(axis=0)
        voxel_indices = np.floor((points - min_coords) / voxel_size).astype(int)
        _, unique_indices = np.unique(voxel_indices, axis=0, return_index=True)
        result = points[unique_indices]
        logger.info(
            "体素网格滤波完成 (NumPy): %d -> %d 点",
            len(points),
            len(result),
        )
        return result

    except MemoryError:
        raise_processing_error(
            ErrorCode.PROCESSING_MEMORY_ERROR,
            "内存不足，无法完成体素网格滤波",
            {"input_points": len(points), "voxel_size": voxel_size},
        )
    except Exception as e:
        raise_processing_error(
            ErrorCode.PROCESSING_ALGORITHM_ERROR,
            f"体素网格滤波失败: {str(e)}",
            {"input_points": len(points), "voxel_size": voxel_size, "error": str(e)},
        )


def statistical_outlier_removal(
    points: np.ndarray,
    nb_neighbors: int = 20,
    std_ratio: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    validate_points(points, "统计离群点移除")
    validate_neighbors(nb_neighbors)
    validate_std_ratio(std_ratio)

    try:
        if HAS_OPEN3D:
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            cleaned, ind = pcd.remove_statistical_outlier(
                nb_neighbors=nb_neighbors,
                std_ratio=std_ratio,
            )
            result = np.asarray(cleaned.points)
            logger.info(
                "统计离群点移除完成: %d -> %d 点 (移除 %d 点)",
                len(points),
                len(result),
                len(points) - len(result),
            )
            return result, np.asarray(ind)

        n = len(points)
        if n < nb_neighbors:
            logger.warning("点数少于邻居数，跳过滤波")
            return points, np.arange(n)

        distances = np.zeros(n)
        for i in range(n):
            diff = points - points[i]
            dists = np.sqrt(np.sum(diff ** 2, axis=1))
            dists = np.sort(dists)
            if n > nb_neighbors:
                distances[i] = np.mean(dists[1:nb_neighbors + 1])
            else:
                distances[i] = np.mean(dists[1:])

        mean_dist = np.mean(distances)
        std_dist = np.std(distances)
        if math.isclose(std_dist, 0.0):
            logger.info("距离标准差为0，返回原始数据")
            return points, np.arange(n)

        threshold = mean_dist + std_ratio * std_dist
        valid_mask = distances <= threshold
        valid_indices = np.where(valid_mask)[0]
        result = points[valid_mask]
        logger.info(
            "统计离群点移除完成 (NumPy): %d -> %d 点",
            len(points),
            len(result),
        )
        return result, valid_indices

    except MemoryError:
        raise_processing_error(
            ErrorCode.PROCESSING_MEMORY_ERROR,
            "内存不足，无法完成统计离群点移除",
            {"input_points": len(points), "nb_neighbors": nb_neighbors},
        )
    except Exception as e:
        raise_processing_error(
            ErrorCode.PROCESSING_ALGORITHM_ERROR,
            f"统计离群点移除失败: {str(e)}",
            {"input_points": len(points), "error": str(e)},
        )


def ransac_plane_segmentation(
    points: np.ndarray,
    distance_threshold: float = 0.01,
    ransac_n: int = 3,
    num_iterations: int = 1000,
    probability: float = 0.999,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    validate_points(points, "RANSAC平面分割")
    validate_distance_threshold(distance_threshold, "RANSAC平面分割")

    if ransac_n < 3:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "RANSAC采样点数至少为3",
            {"ransac_n": ransac_n},
        )

    if num_iterations < 1:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "迭代次数必须至少为1",
            {"num_iterations": num_iterations},
        )

    try:
        if HAS_OPEN3D:
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            plane_model, inliers = pcd.segment_plane(
                distance_threshold=distance_threshold,
                ransac_n=ransac_n,
                num_iterations=num_iterations,
                probability=probability,
            )
            inlier_cloud = pcd.select_by_index(inliers)
            outlier_cloud = pcd.select_by_index(inliers, invert=True)

            result_info = {
                "plane_equation": {
                    "a": float(plane_model[0]),
                    "b": float(plane_model[1]),
                    "c": float(plane_model[2]),
                    "d": float(plane_model[3]),
                },
                "inlier_count": len(inliers),
                "outlier_count": len(points) - len(inliers),
            }
            logger.info(
                "RANSAC平面分割完成: 内点 %d, 外点 %d",
                len(inliers),
                len(points) - len(inliers),
            )
            return np.asarray(outlier_cloud.points), np.asarray(inlier_cloud.points), result_info

        best_inliers = []
        best_plane = [0, 0, 1, 0]
        n = len(points)

        for _ in range(num_iterations):
            sample_indices = np.random.choice(n, min(ransac_n, n), replace=False)
            sample_points = points[sample_indices]

            if len(sample_points) >= 3:
                v1 = sample_points[1] - sample_points[0]
                v2 = sample_points[2] - sample_points[0]
                normal = np.cross(v1, v2)
                norm = np.linalg.norm(normal)
                if norm < 1e-10:
                    continue
                normal = normal / norm
                d = -np.dot(normal, sample_points[0])

                distances = np.abs(np.dot(points, normal) + d)
                inliers = np.where(distances < distance_threshold)[0]

                if len(inliers) > len(best_inliers):
                    best_inliers = inliers
                    best_plane = [float(normal[0]), float(normal[1]), float(normal[2]), float(d)]

        inlier_mask = np.zeros(n, dtype=bool)
        inlier_mask[best_inliers] = True
        outlier_points = points[~inlier_mask]
        inlier_points = points[inlier_mask]

        result_info = {
            "plane_equation": {
                "a": best_plane[0],
                "b": best_plane[1],
                "c": best_plane[2],
                "d": best_plane[3],
            },
            "inlier_count": len(best_inliers),
            "outlier_count": n - len(best_inliers),
        }
        logger.info(
            "RANSAC平面分割完成 (NumPy): 内点 %d, 外点 %d",
            len(best_inliers),
            n - len(best_inliers),
        )
        return outlier_points, inlier_points, result_info

    except MemoryError:
        raise_processing_error(
            ErrorCode.PROCESSING_MEMORY_ERROR,
            "内存不足，无法完成RANSAC平面分割",
            {"input_points": len(points)},
        )
    except Exception as e:
        raise_processing_error(
            ErrorCode.PROCESSING_ALGORITHM_ERROR,
            f"RANSAC平面分割失败: {str(e)}",
            {"input_points": len(points), "error": str(e)},
        )


def icp_registration(
    source_points: np.ndarray,
    target_points: np.ndarray,
    threshold: float = 1.0,
    max_iteration: int = 30,
    init_transform: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    validate_points(source_points, "ICP配准(源)")
    validate_points(target_points, "ICP配准(目标)")
    validate_distance_threshold(threshold, "ICP配准")

    if max_iteration < 1:
        raise_processing_error(
            ErrorCode.PROCESSING_INVALID_PARAMS,
            "最大迭代次数必须至少为1",
            {"max_iteration": max_iteration},
        )

    if init_transform is not None:
        if init_transform.shape != (4, 4):
            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                "初始变换矩阵必须是4×4矩阵",
                {"shape": init_transform.shape},
            )

    try:
        if init_transform is None:
            init_transform = np.eye(4)

        if HAS_OPEN3D:
            source = o3d.geometry.PointCloud()
            source.points = o3d.utility.Vector3dVector(source_points)
            target = o3d.geometry.PointCloud()
            target.points = o3d.utility.Vector3dVector(target_points)

            reg_result = o3d.pipelines.registration.registration_icp(
                source,
                target,
                threshold,
                init_transform,
                o3d.pipelines.registration.TransformationEstimationPointToPoint(),
                o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=max_iteration),
            )

            transformed = np.asarray(source.transform(reg_result.transformation).points)
            result_info = {
                "fitness": float(reg_result.fitness),
                "rmse": float(reg_result.inlier_rmse),
                "transformation": reg_result.transformation.tolist(),
            }
            logger.info(
                "ICP配准完成: fitness=%.4f, rmse=%.4f",
                reg_result.fitness,
                reg_result.inlier_rmse,
            )
            return transformed, reg_result.transformation, result_info

        def compute_transformation(source: np.ndarray, target: np.ndarray) -> np.ndarray:
            centroid_source = np.mean(source, axis=0)
            centroid_target = np.mean(target, axis=0)
            source_centered = source - centroid_source
            target_centered = target - centroid_target
            H = source_centered.T @ target_centered
            U, _, Vt = np.linalg.svd(H)
            R = Vt.T @ U.T
            if np.linalg.det(R) < 0:
                Vt[-1, :] *= -1
                R = Vt.T @ U.T
            t = centroid_target - R @ centroid_source
            transform = np.eye(4)
            transform[:3, :3] = R
            transform[:3, 3] = t
            return transform

        def find_correspondences(source: np.ndarray, target: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
            correspondences = []
            for i, sp in enumerate(source):
                dists = np.sqrt(np.sum((target - sp) ** 2, axis=1))
                min_idx = np.argmin(dists)
                if dists[min_idx] < threshold:
                    correspondences.append((i, min_idx))
            if not correspondences:
                return np.array([], dtype=int), np.array([], dtype=int)
            corr = np.array(correspondences)
            return corr[:, 0], corr[:, 1]

        current_transform = init_transform.copy()
        ones = np.ones((len(source_points), 1))
        source_h = np.hstack([source_points, ones])

        for _ in range(max_iteration):
            transformed = (current_transform @ source_h.T).T[:, :3]
            src_indices, tgt_indices = find_correspondences(transformed, target_points, threshold)

            if len(src_indices) == 0:
                break

            matched_src = transformed[src_indices]
            matched_tgt = target_points[tgt_indices]

            delta_transform = compute_transformation(matched_src, matched_tgt)
            current_transform = delta_transform @ current_transform

        final_transformed = (current_transform @ source_h.T).T[:, :3]
        src_indices, tgt_indices = find_correspondences(final_transformed, target_points, threshold)
        if len(src_indices) > 0:
            matched_src = final_transformed[src_indices]
            matched_tgt = target_points[tgt_indices]
            errors = np.sqrt(np.sum((matched_src - matched_tgt) ** 2, axis=1))
            rmse = float(np.sqrt(np.mean(errors ** 2)))
            fitness = len(src_indices) / len(source_points)
        else:
            rmse = float("inf")
            fitness = 0.0

        result_info = {
            "fitness": fitness,
            "rmse": rmse,
            "transformation": current_transform.tolist(),
        }
        logger.info(
            "ICP配准完成 (NumPy): fitness=%.4f, rmse=%.4f",
            fitness,
            rmse,
        )
        return final_transformed, current_transform, result_info

    except MemoryError:
        raise_processing_error(
            ErrorCode.PROCESSING_MEMORY_ERROR,
            "内存不足，无法完成ICP配准",
            {"source_points": len(source_points), "target_points": len(target_points)},
        )
    except Exception as e:
        raise_processing_error(
            ErrorCode.PROCESSING_ALGORITHM_ERROR,
            f"ICP配准失败: {str(e)}",
            {"source_points": len(source_points), "target_points": len(target_points), "error": str(e)},
        )


def run_advanced_processing(
    points: np.ndarray,
    task_type: str,
    parameters: dict,
    target_points: np.ndarray | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[np.ndarray, dict[str, Any]]:
    validate_points(points, task_type)

    result_info: dict[str, Any] = {}

    try:
        with timeout_handler(timeout_seconds):
            if task_type == "voxel_grid_filter":
                voxel_size = float(parameters.get("voxel_size", 0.05))
                result = voxel_grid_filter(points, voxel_size=voxel_size)
                result_info = {
                    "input_points": len(points),
                    "output_points": len(result),
                    "voxel_size": voxel_size,
                }
                return result, result_info

            if task_type == "statistical_outlier_removal":
                nb_neighbors = int(parameters.get("nb_neighbors", 20))
                std_ratio = float(parameters.get("std_ratio", 2.0))
                result, indices = statistical_outlier_removal(
                    points,
                    nb_neighbors=nb_neighbors,
                    std_ratio=std_ratio,
                )
                result_info = {
                    "input_points": len(points),
                    "output_points": len(result),
                    "removed_points": len(points) - len(result),
                    "nb_neighbors": nb_neighbors,
                    "std_ratio": std_ratio,
                }
                return result, result_info

            if task_type == "ransac_plane_segmentation":
                distance_threshold = float(parameters.get("distance_threshold", 0.01))
                ransac_n = int(parameters.get("ransac_n", 3))
                num_iterations = int(parameters.get("num_iterations", 1000))
                return_inliers = parameters.get("return_inliers", False)

                outlier_points, inlier_points, plane_info = ransac_plane_segmentation(
                    points,
                    distance_threshold=distance_threshold,
                    ransac_n=ransac_n,
                    num_iterations=num_iterations,
                )
                result_info = {**plane_info, "distance_threshold": distance_threshold}

                if return_inliers:
                    return inlier_points, result_info
                return outlier_points, result_info

            if task_type == "icp_registration":
                if target_points is None or target_points.size == 0:
                    raise_processing_error(
                        ErrorCode.PROCESSING_INVALID_PARAMS,
                        "ICP 配准需要提供目标点云",
                        {"target_points": "None or empty"},
                    )

                threshold = float(parameters.get("threshold", 1.0))
                max_iteration = int(parameters.get("max_iteration", 30))
                init_transform = parameters.get("init_transform")
                if init_transform is not None:
                    init_transform = np.array(init_transform)

                transformed, transform_matrix, icp_info = icp_registration(
                    points,
                    target_points,
                    threshold=threshold,
                    max_iteration=max_iteration,
                    init_transform=init_transform,
                )
                return transformed, icp_info

            raise_processing_error(
                ErrorCode.PROCESSING_INVALID_PARAMS,
                f"不支持的处理类型: {task_type}",
                {
                    "supported_types": [
                        "voxel_grid_filter",
                        "statistical_outlier_removal",
                        "ransac_plane_segmentation",
                        "icp_registration",
                    ],
                },
            )

    except TimeoutError as e:
        raise_processing_error(
            ErrorCode.PROCESSING_TIMEOUT,
            str(e),
            {"task_type": task_type, "timeout_seconds": timeout_seconds},
        )

    raise RuntimeError("unreachable")
