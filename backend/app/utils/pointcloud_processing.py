from __future__ import annotations

import logging
from typing import Tuple

import numpy as np

try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False

logger = logging.getLogger(__name__)


def numpy_to_open3d(points: np.ndarray) -> o3d.geometry.PointCloud:
    """Convert numpy array to Open3D PointCloud"""
    if not OPEN3D_AVAILABLE:
        raise ImportError("Open3D is not available")
    
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    return pcd


def open3d_to_numpy(pcd: o3d.geometry.PointCloud) -> np.ndarray:
    """Convert Open3D PointCloud to numpy array"""
    return np.asarray(pcd.points, dtype=np.float64)


def voxel_grid_filter(points: np.ndarray, voxel_size: float = 0.05) -> np.ndarray:
    """
    Voxel Grid 下采样滤波
    :param points: 输入点云 (N, 3)
    :param voxel_size: 体素大小
    :return: 降采样后的点云
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, using random downsample")
        ratio = min(0.5, voxel_size * 10)
        sample_size = max(1, int(points.shape[0] * ratio))
        indices = np.random.choice(points.shape[0], sample_size, replace=False)
        return points[indices]
    
    pcd = numpy_to_open3d(points)
    downsampled = pcd.voxel_down_sample(voxel_size=voxel_size)
    return open3d_to_numpy(downsampled)


def statistical_outlier_removal(
    points: np.ndarray, 
    nb_neighbors: int = 20, 
    std_ratio: float = 2.0
) -> np.ndarray:
    """
    统计离群点移除
    :param points: 输入点云 (N, 3)
    :param nb_neighbors: 用于估计的邻居数量
    :param std_ratio: 标准差阈值
    :return: 移除离群点后的点云
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, using simple z-score filter")
        z = points[:, 2]
        mean = np.mean(z)
        std = np.std(z)
        if np.isclose(std, 0.0):
            return points
        mask = np.abs((z - mean) / std) <= std_ratio
        return points[mask]
    
    pcd = numpy_to_open3d(points)
    cl, ind = pcd.remove_statistical_outlier(
        nb_neighbors=nb_neighbors,
        std_ratio=std_ratio
    )
    inlier_cloud = pcd.select_by_index(ind)
    return open3d_to_numpy(inlier_cloud)


def ransac_plane_segmentation(
    points: np.ndarray,
    distance_threshold: float = 0.01,
    ransac_n: int = 3,
    num_iterations: int = 1000,
    return_plane: bool = False
) -> Tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """
    RANSAC 平面分割
    :param points: 输入点云 (N, 3)
    :param distance_threshold: 距离阈值
    :param ransac_n: 初始采样点数
    :param num_iterations: 迭代次数
    :param return_plane: 是否返回平面参数
    :return: (平面内点, 平面外点, 平面参数[a,b,c,d])
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, returning original points")
        if return_plane:
            return points, np.empty((0, 3)), None
        return points, np.empty((0, 3))
    
    pcd = numpy_to_open3d(points)
    plane_model, inliers = pcd.segment_plane(
        distance_threshold=distance_threshold,
        ransac_n=ransac_n,
        num_iterations=num_iterations
    )
    
    inlier_cloud = pcd.select_by_index(inliers)
    outlier_cloud = pcd.select_by_index(inliers, invert=True)
    
    inlier_points = open3d_to_numpy(inlier_cloud)
    outlier_points = open3d_to_numpy(outlier_cloud)
    
    if return_plane:
        return inlier_points, outlier_points, plane_model
    return inlier_points, outlier_points


def icp_registration(
    source_points: np.ndarray,
    target_points: np.ndarray,
    threshold: float = 0.02,
    max_iterations: int = 100,
    init_transformation: np.ndarray | None = None
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    ICP 点云配准
    :param source_points: 源点云 (N, 3)
    :param target_points: 目标点云 (M, 3)
    :param threshold: 对应点距离阈值
    :param max_iterations: 最大迭代次数
    :param init_transformation: 初始变换矩阵 (4x4)
    :return: (配准后的源点云, 变换矩阵, 配准得分)
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, returning source points")
        identity = np.eye(4)
        return source_points, identity, 0.0
    
    source = numpy_to_open3d(source_points)
    target = numpy_to_open3d(target_points)
    
    # 计算法线
    source.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
    target.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
    
    if init_transformation is None:
        init_transformation = np.eye(4)
    
    # 执行ICP配准
    reg_p2p = o3d.pipelines.registration.registration_icp(
        source, target, threshold, init_transformation,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=max_iterations)
    )
    
    # 应用变换
    source_transformed = source.transform(reg_p2p.transformation)
    transformed_points = open3d_to_numpy(source_transformed)
    
    return transformed_points, reg_p2p.transformation, reg_p2p.fitness


def compute_normal(points: np.ndarray, radius: float = 0.1, max_nn: int = 30) -> np.ndarray:
    """
    计算点云法线
    :param points: 输入点云 (N, 3)
    :param radius: 搜索半径
    :param max_nn: 最大邻居数
    :return: 法向量 (N, 3)
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, returning zero normals")
        return np.zeros_like(points)
    
    pcd = numpy_to_open3d(points)
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=max_nn)
    )
    return np.asarray(pcd.normals, dtype=np.float64)


def passthrough_filter(
    points: np.ndarray,
    axis: str = 'z',
    min_val: float | None = None,
    max_val: float | None = None
) -> np.ndarray:
    """
    直通滤波
    :param points: 输入点云 (N, 3)
    :param axis: 滤波轴 ('x', 'y', 'z')
    :param min_val: 最小值
    :param max_val: 最大值
    :return: 滤波后的点云
    """
    axis_map = {'x': 0, 'y': 1, 'z': 2}
    axis_idx = axis_map.get(axis.lower(), 2)
    
    mask = np.ones(len(points), dtype=bool)
    
    if min_val is not None:
        mask = mask & (points[:, axis_idx] >= min_val)
    if max_val is not None:
        mask = mask & (points[:, axis_idx] <= max_val)
    
    return points[mask]
