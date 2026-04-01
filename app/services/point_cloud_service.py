import os
import time
import asyncio
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
import open3d as o3d

try:
    import laspy
    HAS_LASPY = True
except ImportError:
    HAS_LASPY = False

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.core.exceptions import ProcessingError, InvalidFileTypeError
from app.db.models import PointCloud, ProcessingJob, JobStatus, ProcessingType

logger = get_logger(__name__)
settings = get_settings()

# 支持的文件格式
SUPPORTED_FORMATS = {'.las', '.laz', '.ply', '.pcd', '.xyz', '.pts'}


class PointCloudService:
    def __init__(self):
        self.upload_dir = Path(settings.upload_dir)
        self.processed_dir = Path(settings.processed_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_file(self, filename: str, file_size: int) -> None:
        """验证文件类型和大小"""
        ext = Path(filename).suffix.lower()
        
        if ext not in SUPPORTED_FORMATS:
            raise InvalidFileTypeError(
                f"不支持的文件类型: {ext}",
                details={"supported_formats": list(SUPPORTED_FORMATS)}
            )
        
        if file_size > settings.max_file_size:
            raise InvalidFileTypeError(
                f"文件过大: {file_size} bytes",
                details={
                    "max_size": settings.max_file_size,
                    "file_size": file_size
                }
            )
    
    def get_file_format(self, filename: str) -> str:
        """获取文件格式"""
        return Path(filename).suffix.lower().lstrip('.')
    
    async def read_point_cloud(self, file_path: str) -> o3d.geometry.PointCloud:
        """读取点云文件"""
        ext = Path(file_path).suffix.lower()
        
        try:
            if ext in ['.las', '.laz']:
                if not HAS_LASPY:
                    raise ProcessingError("laspy 库未安装，无法读取 LAS/LAZ 文件")
                return await self._read_las(file_path)
            elif ext == '.ply':
                return await asyncio.to_thread(o3d.io.read_point_cloud, file_path)
            elif ext == '.pcd':
                return await asyncio.to_thread(o3d.io.read_point_cloud, file_path)
            elif ext in ['.xyz', '.pts']:
                return await asyncio.to_thread(o3d.io.read_point_cloud, file_path)
            else:
                raise InvalidFileTypeError(f"不支持的文件格式: {ext}")
        except Exception as e:
            logger.error(f"读取点云文件失败: {file_path}, 错误: {str(e)}")
            raise ProcessingError(f"读取点云文件失败: {str(e)}")
    
    async def _read_las(self, file_path: str) -> o3d.geometry.PointCloud:
        """读取 LAS/LAZ 文件"""
        def _read():
            las = laspy.read(file_path)
            points = np.vstack((las.x, las.y, las.z)).transpose()
            
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            
            # 如果有颜色信息
            if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
                colors = np.vstack((las.red, las.green, las.blue)).transpose()
                colors = colors / 65535.0  # LAS 颜色通常是 16-bit
                pcd.colors = o3d.utility.Vector3dVector(colors)
            
            return pcd
        
        return await asyncio.to_thread(_read)
    
    async def save_point_cloud(
        self,
        pcd: o3d.geometry.PointCloud,
        output_path: str,
        format: str = 'ply'
    ) -> str:
        """保存点云文件"""
        try:
            await asyncio.to_thread(o3d.io.write_point_cloud, output_path, pcd)
            return output_path
        except Exception as e:
            logger.error(f"保存点云文件失败: {output_path}, 错误: {str(e)}")
            raise ProcessingError(f"保存点云文件失败: {str(e)}")
    
    async def get_point_cloud_info(self, pcd: o3d.geometry.PointCloud) -> Dict[str, Any]:
        """获取点云信息"""
        points = np.asarray(pcd.points)
        
        info = {
            "point_count": len(points),
            "has_colors": pcd.has_colors(),
            "has_normals": pcd.has_normals(),
        }
        
        if len(points) > 0:
            bbox = pcd.get_axis_aligned_bounding_box()
            info["bbox_min"] = bbox.min_bound.tolist()
            info["bbox_max"] = bbox.max_bound.tolist()
        
        return info
    
    async def filter_statistical_outlier(
        self,
        pcd: o3d.geometry.PointCloud,
        nb_neighbors: int = 20,
        std_ratio: float = 2.0
    ) -> Tuple[o3d.geometry.PointCloud, List[int]]:
        """统计滤波 - 去除离群点"""
        try:
            cl, ind = await asyncio.to_thread(
                pcd.remove_statistical_outlier,
                nb_neighbors=nb_neighbors,
                std_ratio=std_ratio
            )
            return cl, ind
        except Exception as e:
            logger.error(f"统计滤波失败: {str(e)}")
            raise ProcessingError(f"统计滤波失败: {str(e)}")
    
    async def filter_radius_outlier(
        self,
        pcd: o3d.geometry.PointCloud,
        nb_points: int = 16,
        radius: float = 0.05
    ) -> Tuple[o3d.geometry.PointCloud, List[int]]:
        """半径滤波"""
        try:
            cl, ind = await asyncio.to_thread(
                pcd.remove_radius_outlier,
                nb_points=nb_points,
                radius=radius
            )
            return cl, ind
        except Exception as e:
            logger.error(f"半径滤波失败: {str(e)}")
            raise ProcessingError(f"半径滤波失败: {str(e)}")
    
    async def downsample_voxel(
        self,
        pcd: o3d.geometry.PointCloud,
        voxel_size: float = 0.01
    ) -> o3d.geometry.PointCloud:
        """体素降采样"""
        try:
            return await asyncio.to_thread(pcd.voxel_down_sample, voxel_size=voxel_size)
        except Exception as e:
            logger.error(f"体素降采样失败: {str(e)}")
            raise ProcessingError(f"体素降采样失败: {str(e)}")
    
    async def estimate_normals(
        self,
        pcd: o3d.geometry.PointCloud,
        search_param: Optional[o3d.geometry.KDTreeSearchParam] = None
    ) -> o3d.geometry.PointCloud:
        """估计法向量"""
        try:
            if search_param is None:
                search_param = o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
            
            await asyncio.to_thread(pcd.estimate_normals, search_param=search_param)
            await asyncio.to_thread(pcd.orient_normals_consistent_tangent_plane, k=10)
            return pcd
        except Exception as e:
            logger.error(f"法向量估计失败: {str(e)}")
            raise ProcessingError(f"法向量估计失败: {str(e)}")
    
    async def segment_plane(
        self,
        pcd: o3d.geometry.PointCloud,
        distance_threshold: float = 0.01,
        ransac_n: int = 3,
        num_iterations: int = 1000
    ) -> Tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, List[int]]:
        """平面分割（RANSAC）"""
        try:
            plane_model, inliers = await asyncio.to_thread(
                pcd.segment_plane,
                distance_threshold=distance_threshold,
                ransac_n=ransac_n,
                num_iterations=num_iterations
            )
            
            inlier_cloud = pcd.select_by_index(inliers)
            outlier_cloud = pcd.select_by_index(inliers, invert=True)
            
            return inlier_cloud, outlier_cloud, inliers
        except Exception as e:
            logger.error(f"平面分割失败: {str(e)}")
            raise ProcessingError(f"平面分割失败: {str(e)}")
    
    async def cluster_dbscan(
        self,
        pcd: o3d.geometry.PointCloud,
        eps: float = 0.02,
        min_points: int = 10
    ) -> Tuple[o3d.geometry.PointCloud, np.ndarray]:
        """DBSCAN 聚类分割"""
        try:
            if not pcd.has_normals():
                pcd = await self.estimate_normals(pcd)
            
            labels = await asyncio.to_thread(
                pcd.cluster_dbscan,
                eps=eps,
                min_points=min_points,
                print_progress=False
            )
            
            labels = np.array(labels)
            max_label = labels.max()
            
            logger.info(f"DBSCAN 聚类完成，发现 {max_label + 1} 个簇")
            
            colors = plt.get_cmap("tab20")(labels / (max_label if max_label > 0 else 1))
            colors[labels < 0] = 0  # 噪声点设为黑色
            pcd.colors = o3d.utility.Vector3dVector(colors[:, :3])
            
            return pcd, labels
        except Exception as e:
            logger.error(f"DBSCAN 聚类失败: {str(e)}")
            raise ProcessingError(f"DBSCAN 聚类失败: {str(e)}")
    
    async def register_icp(
        self,
        source: o3d.geometry.PointCloud,
        target: o3d.geometry.PointCloud,
        threshold: float = 0.02,
        trans_init: Optional[np.ndarray] = None
    ) -> Tuple[np.ndarray, float]:
        """ICP 配准"""
        try:
            if trans_init is None:
                trans_init = np.eye(4)
            
            reg_p2p = await asyncio.to_thread(
                o3d.pipelines.registration.registration_icp,
                source, target, threshold, trans_init,
                o3d.pipelines.registration.TransformationEstimationPointToPoint()
            )
            
            return reg_p2p.transformation, reg_p2p.fitness
        except Exception as e:
            logger.error(f"ICP 配准失败: {str(e)}")
            raise ProcessingError(f"ICP 配准失败: {str(e)}")
    
    async def process_point_cloud(
        self,
        job: ProcessingJob,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """处理点云的主函数"""
        start_time = time.time()
        
        try:
            # 读取点云
            if progress_callback:
                await progress_callback(10)
            
            pcd = await self.read_point_cloud(job.point_cloud.file_path)
            original_info = await self.get_point_cloud_info(pcd)
            logger.info(f"读取点云完成: {original_info['point_count']} 点")
            
            result_info = {
                "original": original_info,
                "processing_steps": []
            }
            
            # 根据处理类型执行不同操作
            if job.processing_type == ProcessingType.FILTER:
                pcd, result_info = await self._apply_filter(pcd, job.parameters, result_info)
                
            elif job.processing_type == ProcessingType.SEGMENT:
                pcd, result_info = await self._apply_segmentation(pcd, job.parameters, result_info)
                
            elif job.processing_type == ProcessingType.DOWNSAMPLE:
                pcd, result_info = await self._apply_downsampling(pcd, job.parameters, result_info)
                
            elif job.processing_type == ProcessingType.REGISTER:
                result_info = await self._apply_registration(pcd, job.parameters, result_info)
            
            if progress_callback:
                await progress_callback(80)
            
            # 保存处理结果
            output_filename = f"processed_{job.id}_{job.point_cloud.name}"
            output_path = self.processed_dir / output_filename
            
            if job.processing_type != ProcessingType.REGISTER:
                await self.save_point_cloud(pcd, str(output_path))
                result_info["output_file"] = str(output_path)
                
                processed_info = await self.get_point_cloud_info(pcd)
                result_info["processed"] = processed_info
            
            if progress_callback:
                await progress_callback(100)
            
            result_info["processing_duration"] = time.time() - start_time
            
            return result_info
            
        except Exception as e:
            logger.error(f"点云处理失败: {str(e)}")
            raise ProcessingError(f"点云处理失败: {str(e)}")
    
    async def _apply_filter(
        self,
        pcd: o3d.geometry.PointCloud,
        parameters: Dict[str, Any],
        result_info: Dict[str, Any]
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """应用滤波"""
        filter_type = parameters.get("filter_type", "statistical")
        
        if filter_type == "statistical":
            nb_neighbors = parameters.get("nb_neighbors", 20)
            std_ratio = parameters.get("std_ratio", 2.0)
            pcd, indices = await self.filter_statistical_outlier(pcd, nb_neighbors, std_ratio)
            result_info["processing_steps"].append({
                "type": "statistical_outlier_removal",
                "nb_neighbors": nb_neighbors,
                "std_ratio": std_ratio,
                "remaining_points": len(indices)
            })
            
        elif filter_type == "radius":
            nb_points = parameters.get("nb_points", 16)
            radius = parameters.get("radius", 0.05)
            pcd, indices = await self.filter_radius_outlier(pcd, nb_points, radius)
            result_info["processing_steps"].append({
                "type": "radius_outlier_removal",
                "nb_points": nb_points,
                "radius": radius,
                "remaining_points": len(indices)
            })
        
        return pcd, result_info
    
    async def _apply_segmentation(
        self,
        pcd: o3d.geometry.PointCloud,
        parameters: Dict[str, Any],
        result_info: Dict[str, Any]
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """应用分割"""
        segment_type = parameters.get("segment_type", "plane")
        
        if segment_type == "plane":
            distance_threshold = parameters.get("distance_threshold", 0.01)
            inlier_cloud, outlier_cloud, inliers = await self.segment_plane(
                pcd, distance_threshold
            )
            result_info["processing_steps"].append({
                "type": "plane_segmentation",
                "distance_threshold": distance_threshold,
                "inlier_count": len(inliers),
                "outlier_count": len(pcd.points) - len(inliers)
            })
            # 返回非平面点（通常更有用）
            pcd = outlier_cloud
            
        elif segment_type == "dbscan":
            eps = parameters.get("eps", 0.02)
            min_points = parameters.get("min_points", 10)
            pcd, labels = await self.cluster_dbscan(pcd, eps, min_points)
            unique_labels = len(set(labels)) - (1 if -1 in labels else 0)
            result_info["processing_steps"].append({
                "type": "dbscan_clustering",
                "eps": eps,
                "min_points": min_points,
                "cluster_count": unique_labels
            })
        
        return pcd, result_info
    
    async def _apply_downsampling(
        self,
        pcd: o3d.geometry.PointCloud,
        parameters: Dict[str, Any],
        result_info: Dict[str, Any]
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """应用降采样"""
        voxel_size = parameters.get("voxel_size", 0.01)
        original_count = len(pcd.points)
        
        pcd = await self.downsample_voxel(pcd, voxel_size)
        
        result_info["processing_steps"].append({
            "type": "voxel_downsampling",
            "voxel_size": voxel_size,
            "original_count": original_count,
            "downsampled_count": len(pcd.points),
            "reduction_ratio": len(pcd.points) / original_count if original_count > 0 else 0
        })
        
        return pcd, result_info
    
    async def _apply_registration(
        self,
        pcd: o3d.geometry.PointCloud,
        parameters: Dict[str, Any],
        result_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """应用配准"""
        target_path = parameters.get("target_path")
        if not target_path:
            raise ProcessingError("配准需要目标点云路径")
        
        target = await self.read_point_cloud(target_path)
        threshold = parameters.get("threshold", 0.02)
        
        transformation, fitness = await self.register_icp(pcd, target, threshold)
        
        result_info["processing_steps"].append({
            "type": "icp_registration",
            "threshold": threshold,
            "fitness": fitness,
            "transformation": transformation.tolist()
        })
        
        return result_info


# 全局服务实例
point_cloud_service = PointCloudService()
