from __future__ import annotations

import logging
from typing import Tuple, List, Optional

import numpy as np

try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

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


def voxelization(
    points: np.ndarray,
    voxel_size: float = 0.1,
    fill: bool = True
) -> Tuple[np.ndarray, np.ndarray]:
    """
    体素化
    :param points: 输入点云 (N, 3)
    :param voxel_size: 体素大小
    :param fill: 是否填充内部体素
    :return: (体素中心点坐标, 体素网格索引)
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, returning simple voxel centers")
        min_coords = np.min(points, axis=0)
        voxel_indices = np.floor((points - min_coords) / voxel_size).astype(np.int32)
        unique_indices = np.unique(voxel_indices, axis=0)
        voxel_centers = unique_indices.astype(np.float64) * voxel_size + min_coords + voxel_size / 2
        return voxel_centers, unique_indices
    
    pcd = numpy_to_open3d(points)
    voxel_grid = o3d.geometry.VoxelGrid.create_from_point_cloud(pcd, voxel_size=voxel_size)
    
    voxels = voxel_grid.get_voxels()
    voxel_indices = np.array([v.grid_index for v in voxels], dtype=np.int32)
    
    origin = np.array(voxel_grid.origin, dtype=np.float64)
    voxel_centers = voxel_indices.astype(np.float64) * voxel_size + origin + voxel_size / 2
    
    return voxel_centers, voxel_indices


def poisson_surface_reconstruction(
    points: np.ndarray,
    depth: int = 8,
    min_density: float = 0.01,
    point_weight: float = 1.0
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Poisson 表面重建（生成三角网格）
    :param points: 输入点云 (N, 3)
    :param depth: 重建深度，越大越精细
    :param min_density: 最小密度阈值，用于移除低密度的面
    :param point_weight: 点权重
    :return: (顶点坐标, 三角面索引)
    """
    if not OPEN3D_AVAILABLE:
        logger.warning("Open3D not available, returning empty mesh")
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int32)
    
    pcd = numpy_to_open3d(points)
    
    # 估计法线
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
    )
    pcd.orient_normals_consistent_tangent_plane(k=10)
    
    # Poisson 重建
    with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Debug):
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=depth, point_weight=point_weight
        )
    
    # 移除低密度顶点
    if min_density > 0:
        vertices_to_remove = densities < np.quantile(densities, min_density)
        mesh.remove_vertices_by_mask(vertices_to_remove)
    
    # 简化网格
    mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=10000)
    
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int32)
    
    return vertices, triangles


def marching_cubes_reconstruction(
    points: np.ndarray,
    voxel_size: float = 0.1,
    level: float = 0.0,
    offset: float = 0.5
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Marching Cubes 重建
    :param points: 输入点云 (N, 3)
    :param voxel_size: 体素大小
    :param level: 等值面级别
    :param offset: 体素偏移
    :return: (顶点坐标, 三角面索引)
    """
    if not TRIMESH_AVAILABLE and not OPEN3D_AVAILABLE:
        logger.warning("No mesh library available, returning empty mesh")
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int32)
    
    if TRIMESH_AVAILABLE:
        try:
            # 使用 trimesh 的 marching cubes
            from scipy.spatial import cKDTree
            
            # 创建体素网格
            min_coords = np.min(points, axis=0) - voxel_size * 2
            max_coords = np.max(points, axis=0) + voxel_size * 2
            
            # 计算体素索引
            voxels_shape = np.ceil((max_coords - min_coords) / voxel_size).astype(np.int32)
            x, y, z = np.meshgrid(
                np.arange(voxels_shape[0]),
                np.arange(voxels_shape[1]),
                np.arange(voxels_shape[2]),
                indexing='ij'
            )
            voxel_centers = np.stack([x, y, z], axis=-1) * voxel_size + min_coords + voxel_size / 2
            
            # 计算到点云的距离
            tree = cKDTree(points)
            distances, _ = tree.query(voxel_centers.reshape(-1, 3), k=1)
            volume = distances.reshape(voxels_shape)
            
            # Marching Cubes
            vertices, faces = trimesh.voxel.ops.matrix_to_marching_cubes(
                volume < (voxel_size * 1.5),
                pitch=voxel_size,
                origin=min_coords
            )
            
            return vertices.astype(np.float64), faces.astype(np.int32)
        except Exception as e:
            logger.warning(f"Trimesh marching cubes failed: {e}")
    
    if OPEN3D_AVAILABLE:
        try:
            # 使用 Open3D 的 Ball Pivoting
            pcd = numpy_to_open3d(points)
            pcd.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
            )
            
            # 计算用于 Ball Pivoting 的半径
            distances = pcd.compute_nearest_neighbor_distance()
            avg_dist = np.mean(distances)
            radii = [avg_dist * 0.5, avg_dist, avg_dist * 2]
            
            mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
                pcd, o3d.utility.DoubleVector(radii)
            )
            
            vertices = np.asarray(mesh.vertices, dtype=np.float64)
            triangles = np.asarray(mesh.triangles, dtype=np.int32)
            
            return vertices, triangles
        except Exception as e:
            logger.warning(f"Open3D ball pivoting failed: {e}")
    
    return np.empty((0, 3)), np.empty((0, 3), dtype=np.int32)


def write_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    output_path: str,
    file_format: str = "ply"
) -> bool:
    """
    写入网格文件
    :param vertices: 顶点坐标 (V, 3)
    :param faces: 三角面索引 (F, 3)
    :param output_path: 输出路径
    :param file_format: 文件格式 (ply, obj, stl)
    :return: 是否成功
    """
    if not OPEN3D_AVAILABLE and not TRIMESH_AVAILABLE:
        logger.error("No mesh library available for writing")
        return False
    
    try:
        if TRIMESH_AVAILABLE:
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            mesh.export(output_path, file_type=file_format)
            return True
        elif OPEN3D_AVAILABLE:
            mesh = o3d.geometry.TriangleMesh()
            mesh.vertices = o3d.utility.Vector3dVector(vertices.astype(np.float64))
            mesh.triangles = o3d.utility.Vector3iVector(faces.astype(np.int32))
            o3d.io.write_triangle_mesh(output_path, mesh)
            return True
    except Exception as e:
        logger.error(f"Failed to write mesh: {e}")
        return False
    
    return False
