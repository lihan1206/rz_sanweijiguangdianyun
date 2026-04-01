import os
import numpy as np
import open3d as o3d
import pylas
from loguru import logger
from typing import Tuple, Dict, Any
import json

class PointCloudProcessingError(Exception):
    """点云处理异常基类"""
    pass

class FileFormatError(PointCloudProcessingError):
    """文件格式错误"""
    pass

class PointCloudService:
    @staticmethod
    def read_point_cloud(file_path: str) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """读取点云文件，支持 .las 和 .ply 格式"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_ext = os.path.splitext(file_path)[1].lower()
        metadata = {}
        
        try:
            if file_ext == '.ply':
                pcd = o3d.io.read_point_cloud(file_path)
                metadata['format'] = 'ply'
                metadata['point_count'] = len(pcd.points)
                if pcd.has_colors():
                    metadata['has_colors'] = True
                if pcd.has_normals():
                    metadata['has_normals'] = True
                    
            elif file_ext == '.las':
                las = pylas.read(file_path)
                points = np.vstack((las.x, las.y, las.z)).transpose()
                pcd = o3d.geometry.PointCloud()
                pcd.points = o3d.utility.Vector3dVector(points)
                
                if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
                    colors = np.vstack((las.red, las.green, las.blue)).transpose() / 65535.0
                    pcd.colors = o3d.utility.Vector3dVector(colors)
                    metadata['has_colors'] = True
                
                metadata['format'] = 'las'
                metadata['point_count'] = len(points)
                metadata['version'] = f"{las.header.major_version}.{las.header.minor_version}"
                
            else:
                raise FileFormatError(f"Unsupported file format: {file_ext}")
            
            logger.info(f"Successfully read point cloud: {metadata.get('point_count', 0)} points")
            return pcd, metadata
            
        except Exception as e:
            logger.error(f"Error reading point cloud file: {e}")
            raise PointCloudProcessingError(f"Failed to read point cloud: {str(e)}")

    @staticmethod
    def write_point_cloud(pcd: o3d.geometry.PointCloud, output_path: str, format: str = 'ply') -> None:
        """保存点云文件"""
        try:
            o3d.io.write_point_cloud(output_path, pcd)
            logger.info(f"Point cloud saved to: {output_path}")
        except Exception as e:
            logger.error(f"Error saving point cloud: {e}")
            raise PointCloudProcessingError(f"Failed to save point cloud: {str(e)}")

    @staticmethod
    def statistical_outlier_removal(
        pcd: o3d.geometry.PointCloud,
        nb_neighbors: int = 20,
        std_ratio: float = 2.0
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """统计滤波去除离群点"""
        try:
            cl, ind = pcd.remove_statistical_outlier(
                nb_neighbors=nb_neighbors,
                std_ratio=std_ratio
            )
            inlier_cloud = pcd.select_by_index(ind)
            
            stats = {
                'original_points': len(pcd.points),
                'filtered_points': len(inlier_cloud.points),
                'removed_points': len(pcd.points) - len(inlier_cloud.points),
                'filter_type': 'statistical_outlier_removal',
                'parameters': {
                    'nb_neighbors': nb_neighbors,
                    'std_ratio': std_ratio
                }
            }
            
            logger.info(f"Statistical filtering: {stats['removed_points']} points removed")
            return inlier_cloud, stats
            
        except Exception as e:
            logger.error(f"Error in statistical outlier removal: {e}")
            raise PointCloudProcessingError(f"Statistical filtering failed: {str(e)}")

    @staticmethod
    def radius_outlier_removal(
        pcd: o3d.geometry.PointCloud,
        nb_points: int = 16,
        radius: float = 0.05
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """半径滤波去除离群点"""
        try:
            cl, ind = pcd.remove_radius_outlier(
                nb_points=nb_points,
                radius=radius
            )
            inlier_cloud = pcd.select_by_index(ind)
            
            stats = {
                'original_points': len(pcd.points),
                'filtered_points': len(inlier_cloud.points),
                'removed_points': len(pcd.points) - len(inlier_cloud.points),
                'filter_type': 'radius_outlier_removal',
                'parameters': {
                    'nb_points': nb_points,
                    'radius': radius
                }
            }
            
            logger.info(f"Radius filtering: {stats['removed_points']} points removed")
            return inlier_cloud, stats
            
        except Exception as e:
            logger.error(f"Error in radius outlier removal: {e}")
            raise PointCloudProcessingError(f"Radius filtering failed: {str(e)}")

    @staticmethod
    def voxel_downsample(
        pcd: o3d.geometry.PointCloud,
        voxel_size: float = 0.01
    ) -> Tuple[o3d.geometry.PointCloud, Dict[str, Any]]:
        """体素下采样"""
        try:
            downsampled = pcd.voxel_down_sample(voxel_size=voxel_size)
            
            stats = {
                'original_points': len(pcd.points),
                'downsampled_points': len(downsampled.points),
                'filter_type': 'voxel_downsample',
                'parameters': {
                    'voxel_size': voxel_size
                }
            }
            
            logger.info(f"Voxel downsampling: {stats['original_points']} -> {stats['downsampled_points']} points")
            return downsampled, stats
            
        except Exception as e:
            logger.error(f"Error in voxel downsampling: {e}")
            raise PointCloudProcessingError(f"Voxel downsampling failed: {str(e)}")

    @staticmethod
    def segment_plane(
        pcd: o3d.geometry.PointCloud,
        distance_threshold: float = 0.01,
        ransac_n: int = 3,
        num_iterations: int = 1000
    ) -> Tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud, Dict[str, Any]]:
        """平面分割"""
        try:
            plane_model, inliers = pcd.segment_plane(
                distance_threshold=distance_threshold,
                ransac_n=ransac_n,
                num_iterations=num_iterations
            )
            
            inlier_cloud = pcd.select_by_index(inliers)
            outlier_cloud = pcd.select_by_index(inliers, invert=True)
            
            stats = {
                'total_points': len(pcd.points),
                'plane_points': len(inlier_cloud.points),
                'other_points': len(outlier_cloud.points),
                'plane_model': plane_model.tolist(),
                'segmentation_type': 'plane',
                'parameters': {
                    'distance_threshold': distance_threshold,
                    'ransac_n': ransac_n,
                    'num_iterations': num_iterations
                }
            }
            
            logger.info(f"Plane segmentation: {stats['plane_points']} points in plane")
            return inlier_cloud, outlier_cloud, stats
            
        except Exception as e:
            logger.error(f"Error in plane segmentation: {e}")
            raise PointCloudProcessingError(f"Plane segmentation failed: {str(e)}")

    @staticmethod
    def cluster_dbscan(
        pcd: o3d.geometry.PointCloud,
        eps: float = 0.02,
        min_points: int = 10
    ) -> Tuple[Dict[int, o3d.geometry.PointCloud], Dict[str, Any]]:
        """DBSCAN聚类分割"""
        try:
            labels = np.array(pcd.cluster_dbscan(eps=eps, min_points=min_points))
            max_label = labels.max()
            
            clusters = {}
            for i in range(max_label + 1):
                cluster_indices = np.where(labels == i)[0]
                clusters[i] = pcd.select_by_index(cluster_indices)
            
            stats = {
                'total_points': len(pcd.points),
                'cluster_count': max_label + 1,
                'noise_points': len(np.where(labels == -1)[0]),
                'clustering_type': 'dbscan',
                'parameters': {
                    'eps': eps,
                    'min_points': min_points
                }
            }
            
            logger.info(f"DBSCAN clustering: {stats['cluster_count']} clusters found")
            return clusters, stats
            
        except Exception as e:
            logger.error(f"Error in DBSCAN clustering: {e}")
            raise PointCloudProcessingError(f"DBSCAN clustering failed: {str(e)}")

    @staticmethod
    def process_point_cloud(
        input_path: str,
        output_dir: str,
        operations: list = None
    ) -> Dict[str, Any]:
        """
        处理点云的主函数
        operations: 操作列表，每个操作是包含 'type' 和 'parameters' 的字典
        """
        if operations is None:
            operations = [
                {'type': 'statistical_outlier_removal', 'parameters': {}},
                {'type': 'voxel_downsample', 'parameters': {'voxel_size': 0.01}}
            ]
        
        results = {
            'input_path': input_path,
            'output_dir': output_dir,
            'operations': [],
            'total_processing_time': 0,
            'success': False
        }
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            pcd, metadata = PointCloudService.read_point_cloud(input_path)
            results['metadata'] = metadata
            
            current_pcd = pcd
            
            for operation in operations:
                op_type = operation['type']
                op_params = operation.get('parameters', {})
                
                if op_type == 'statistical_outlier_removal':
                    current_pcd, stats = PointCloudService.statistical_outlier_removal(current_pcd, **op_params)
                elif op_type == 'radius_outlier_removal':
                    current_pcd, stats = PointCloudService.radius_outlier_removal(current_pcd, **op_params)
                elif op_type == 'voxel_downsample':
                    current_pcd, stats = PointCloudService.voxel_downsample(current_pcd, **op_params)
                elif op_type == 'segment_plane':
                    plane_pcd, other_pcd, stats = PointCloudService.segment_plane(current_pcd, **op_params)
                    plane_output = os.path.join(output_dir, f"plane_segment.ply")
                    PointCloudService.write_point_cloud(plane_pcd, plane_output)
                    other_output = os.path.join(output_dir, f"other_segment.ply")
                    PointCloudService.write_point_cloud(other_pcd, other_output)
                elif op_type == 'cluster_dbscan':
                    clusters, stats = PointCloudService.cluster_dbscan(current_pcd, **op_params)
                    for cluster_id, cluster_pcd in clusters.items():
                        cluster_output = os.path.join(output_dir, f"cluster_{cluster_id}.ply")
                        PointCloudService.write_point_cloud(cluster_pcd, cluster_output)
                else:
                    logger.warning(f"Unknown operation type: {op_type}")
                    continue
                
                results['operations'].append({
                    'type': op_type,
                    'stats': stats
                })
            
            final_output = os.path.join(output_dir, "processed_point_cloud.ply")
            PointCloudService.write_point_cloud(current_pcd, final_output)
            results['final_output'] = final_output
            results['final_point_count'] = len(current_pcd.points)
            results['success'] = True
            
            with open(os.path.join(output_dir, "processing_results.json"), 'w') as f:
                json.dump(results, f, indent=2)
            
            logger.info("Point cloud processing completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Point cloud processing failed: {e}")
            results['error'] = str(e)
            raise PointCloudProcessingError(f"Processing failed: {str(e)}")
