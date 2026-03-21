import open3d as o3d
import numpy as np
import os
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
import laspy
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PointCloudProcessor:
    """点云处理服务"""
    
    def __init__(self, processed_dir: str = "./processed"):
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def load_point_cloud(self, file_path: str) -> o3d.geometry.PointCloud:
        """加载点云文件"""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        
        if suffix == '.ply':
            pcd = o3d.io.read_point_cloud(str(file_path))
        elif suffix in ['.las', '.laz']:
            pcd = self._load_las(str(file_path))
        elif suffix == '.xyz':
            pcd = o3d.io.read_point_cloud(str(file_path), format='xyz')
        elif suffix == '.pcd':
            pcd = o3d.io.read_point_cloud(str(file_path))
        elif suffix == '.obj':
            mesh = o3d.io.read_triangle_mesh(str(file_path))
            pcd = mesh.sample_points_uniformly(number_of_points=len(mesh.vertices))
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
        
        if len(pcd.points) == 0:
            raise ValueError("Point cloud is empty")
        
        return pcd
    
    def _load_las(self, file_path: str) -> o3d.geometry.PointCloud:
        """加载LAS/LAZ文件"""
        las = laspy.read(file_path)
        
        points = np.vstack((las.x, las.y, las.z)).transpose()
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        
        # 读取颜色（如果有）
        if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
            colors = np.vstack((las.red, las.green, las.blue)).transpose()
            # LAS颜色通常是16位的，需要归一化到0-1
            colors = colors / 65535.0
            pcd.colors = o3d.utility.Vector3dVector(colors)
        
        # 读取强度（作为额外属性）
        if hasattr(las, 'intensity'):
            intensities = np.array(las.intensity).reshape(-1, 1)
            # 可以存储为自定义属性
        
        return pcd
    
    def save_point_cloud(self, pcd: o3d.geometry.PointCloud, file_path: str, format: str = 'ply'):
        """保存点云文件"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format.lower() == 'ply':
            o3d.io.write_point_cloud(str(file_path), pcd, write_ascii=False)
        elif format.lower() == 'xyz':
            o3d.io.write_point_cloud(str(file_path), pcd, write_ascii=True)
        elif format.lower() == 'obj':
            # OBJ格式需要转换为mesh，这里简单处理为点云
            o3d.io.write_point_cloud(str(file_path), pcd, write_ascii=True)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def get_point_cloud_info(self, pcd: o3d.geometry.PointCloud) -> Dict[str, Any]:
        """获取点云信息"""
        points = np.asarray(pcd.points)
        
        info = {
            "point_count": len(points),
            "has_color": pcd.has_colors(),
            "has_normal": pcd.has_normals(),
            "bounding_box": {
                "min": points.min(axis=0).tolist(),
                "max": points.max(axis=0).tolist()
            }
        }
        
        return info
    
    def voxel_filter(self, pcd: o3d.geometry.PointCloud, voxel_size: float) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """Voxel Grid下采样滤波"""
        original_count = len(pcd.points)
        
        # 执行体素下采样
        downsampled = pcd.voxel_down_sample(voxel_size=voxel_size)
        
        result_count = len(downsampled.points)
        reduction_ratio = (original_count - result_count) / original_count * 100
        
        summary = {
            "input_points": original_count,
            "output_points": result_count,
            "reduction_ratio": round(reduction_ratio, 2),
            "voxel_size": voxel_size,
            "processing_time": 0  # 由调用方填充
        }
        
        logger.info(f"Voxel filter: {original_count} -> {result_count} points ({reduction_ratio:.1f}% reduction)")
        
        return downsampled, summary
    
    def statistical_outlier_removal(self, pcd: o3d.geometry.PointCloud, 
                                    nb_neighbors: int = 20, 
                                    std_ratio: float = 2.0) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """统计滤波去除离群点"""
        original_count = len(pcd.points)
        
        # 执行统计滤波
        filtered, inlier_indices = pcd.remove_statistical_outlier(
            nb_neighbors=nb_neighbors,
            std_ratio=std_ratio
        )
        
        result_count = len(filtered.points)
        removed_count = original_count - result_count
        
        summary = {
            "input_points": original_count,
            "output_points": result_count,
            "removed_points": removed_count,
            "removal_ratio": round(removed_count / original_count * 100, 2),
            "nb_neighbors": nb_neighbors,
            "std_ratio": std_ratio,
            "processing_time": 0
        }
        
        logger.info(f"Statistical filter: removed {removed_count} outliers ({removed_count/original_count*100:.1f}%)")
        
        return filtered, summary
    
    def ransac_plane_segmentation(self, pcd: o3d.geometry.PointCloud,
                                  distance_threshold: float = 0.01,
                                  ransac_n: int = 3,
                                  num_iterations: int = 1000) -> Tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, Dict[str, Any]]:
        """RANSAC平面分割"""
        original_count = len(pcd.points)
        
        # 执行平面分割
        plane_model, inliers = pcd.segment_plane(
            distance_threshold=distance_threshold,
            ransac_n=ransac_n,
            num_iterations=num_iterations
        )
        
        # 提取平面点和非平面点
        plane_cloud = pcd.select_by_index(inliers)
        non_plane_cloud = pcd.select_by_index(inliers, invert=True)
        
        # 给平面点上色（红色）
        plane_cloud.paint_uniform_color([1.0, 0.0, 0.0])
        
        # 合并结果（平面点为红色，非平面点保持原色或设为灰色）
        if not non_plane_cloud.has_colors():
            non_plane_cloud.paint_uniform_color([0.7, 0.7, 0.7])
        
        result_cloud = plane_cloud + non_plane_cloud
        
        a, b, c, d = plane_model
        summary = {
            "input_points": original_count,
            "plane_points": len(plane_cloud.points),
            "non_plane_points": len(non_plane_cloud.points),
            "plane_equation": {"a": a, "b": b, "c": c, "d": d},
            "distance_threshold": distance_threshold,
            "processing_time": 0
        }
        
        logger.info(f"RANSAC segmentation: plane={len(plane_cloud.points)}, non-plane={len(non_plane_cloud.points)}")
        
        return result_cloud, plane_cloud, summary
    
    def icp_registration(self, source_pcd: o3d.geometry.PointCloud,
                         target_pcd: o3d.geometry.PointCloud,
                         max_correspondence_distance: float = 0.05,
                         init_transform: Optional[np.ndarray] = None,
                         max_iterations: int = 30) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """ICP点云配准"""
        if init_transform is None:
            init_transform = np.eye(4)
        
        # 估计法线（ICP需要）
        source_pcd.estimate_normals()
        target_pcd.estimate_normals()
        
        # 执行ICP
        result = o3d.pipelines.registration.registration_icp(
            source_pcd,
            target_pcd,
            max_correspondence_distance,
            init_transform,
            o3d.pipelines.registration.TransformationEstimationPointToPlane(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=max_iterations)
        )
        
        # 应用变换
        registered_pcd = source_pcd.transform(result.transformation)
        
        summary = {
            "fitness": result.fitness,
            "inlier_rmse": result.inlier_rmse,
            "correspondence_set_size": len(result.correspondence_set),
            "transformation": result.transformation.tolist(),
            "max_correspondence_distance": max_correspondence_distance,
            "max_iterations": max_iterations,
            "processing_time": 0
        }
        
        logger.info(f"ICP registration: fitness={result.fitness:.4f}, RMSE={result.inlier_rmse:.4f}")
        
        return registered_pcd, summary
    
    def convert_to_binary_data(self, pcd: o3d.geometry.PointCloud, max_points: Optional[int] = None) -> Dict[str, Any]:
        """将点云转换为二进制数据（用于前端可视化）"""
        points = np.asarray(pcd.points)
        
        # 下采样（如果点数过多）
        if max_points and len(points) > max_points:
            indices = np.random.choice(len(points), max_points, replace=False)
            points = points[indices]
            colors = np.asarray(pcd.colors)[indices] if pcd.has_colors() else None
            normals = np.asarray(pcd.normals)[indices] if pcd.has_normals() else None
        else:
            colors = np.asarray(pcd.colors) if pcd.has_colors() else None
            normals = np.asarray(pcd.normals) if pcd.has_normals() else None
        
        result = {
            "points": points.astype(np.float32).tobytes(),
            "point_count": len(points),
            "has_color": colors is not None,
            "has_normal": normals is not None,
            "bounding_box": {
                "min": points.min(axis=0).tolist(),
                "max": points.max(axis=0).tolist()
            }
        }
        
        if colors is not None:
            result["colors"] = (colors * 255).astype(np.uint8).tobytes()
        
        if normals is not None:
            result["normals"] = normals.astype(np.float32).tobytes()
        
        return result
    
    def process_task(self, task_type: str, input_path: str, output_path: str, 
                     parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理任务入口"""
        import time
        start_time = time.time()
        
        # 加载点云
        pcd = self.load_point_cloud(input_path)
        
        # 根据任务类型执行处理
        if task_type == "filter_voxel":
            voxel_size = parameters.get("voxel_size", 0.05)
            result_pcd, summary = self.voxel_filter(pcd, voxel_size)
        
        elif task_type == "filter_statistical":
            nb_neighbors = parameters.get("nb_neighbors", 20)
            std_ratio = parameters.get("std_ratio", 2.0)
            result_pcd, summary = self.statistical_outlier_removal(pcd, nb_neighbors, std_ratio)
        
        elif task_type == "segment_ransac":
            distance_threshold = parameters.get("distance_threshold", 0.01)
            ransac_n = parameters.get("ransac_n", 3)
            num_iterations = parameters.get("num_iterations", 1000)
            result_pcd, _, summary = self.ransac_plane_segmentation(
                pcd, distance_threshold, ransac_n, num_iterations
            )
        
        elif task_type == "register_icp":
            target_path = parameters.get("target_path")
            if not target_path or not os.path.exists(target_path):
                raise ValueError("Target point cloud not found")
            
            target_pcd = self.load_point_cloud(target_path)
            max_correspondence_distance = parameters.get("max_correspondence_distance", 0.05)
            init_transform = parameters.get("init_transform")
            if init_transform:
                init_transform = np.array(init_transform)
            max_iterations = parameters.get("max_iterations", 30)
            
            result_pcd, summary = self.icp_registration(
                pcd, target_pcd, max_correspondence_distance, init_transform, max_iterations
            )
        
        else:
            raise ValueError(f"Unknown task type: {task_type}")
        
        # 保存结果
        self.save_point_cloud(result_pcd, output_path)
        
        # 计算处理时间
        processing_time = time.time() - start_time
        summary["processing_time"] = round(processing_time, 2)
        
        # 添加输出文件信息
        summary["output_file"] = output_path
        summary["output_file_size"] = os.path.getsize(output_path)
        
        return summary


# 全局处理器实例
processor = PointCloudProcessor()
