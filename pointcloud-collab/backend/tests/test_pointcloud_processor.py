"""
点云处理功能测试
"""
import pytest
import numpy as np
import open3d as o3d
import tempfile
import os
from pathlib import Path

from app.services.pointcloud_processor import PointCloudProcessor


@pytest.fixture
def sample_point_cloud():
    """创建示例点云"""
    # 创建一个包含噪声的平面点云
    np.random.seed(42)
    
    # 创建平面点云
    x = np.random.uniform(-5, 5, 1000)
    y = np.random.uniform(-5, 5, 1000)
    z = np.zeros(1000)
    
    # 添加噪声
    z += np.random.normal(0, 0.01, 1000)
    
    # 添加一些离群点
    outlier_indices = np.random.choice(1000, 50, replace=False)
    z[outlier_indices] += np.random.uniform(0.5, 2, 50)
    
    points = np.column_stack([x, y, z])
    
    # 创建颜色
    colors = np.random.rand(1000, 3)
    
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(colors)
    
    return pcd


@pytest.fixture
def temp_ply_file(sample_point_cloud):
    """创建临时PLY文件"""
    with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as f:
        temp_path = f.name
    
    o3d.io.write_point_cloud(temp_path, sample_point_cloud)
    yield temp_path
    
    # 清理
    if os.path.exists(temp_path):
        os.remove(temp_path)


class TestPointCloudProcessor:
    """点云处理器测试类"""
    
    def test_load_ply(self, temp_ply_file):
        """测试加载PLY文件"""
        processor = PointCloudProcessor(temp_ply_file)
        pcd = processor.load()
        
        assert pcd is not None
        assert len(pcd.points) == 1000
        assert pcd.has_colors()
    
    def test_get_info(self, temp_ply_file):
        """测试获取点云信息"""
        processor = PointCloudProcessor(temp_ply_file)
        info = processor.get_info()
        
        assert info["point_count"] == 1000
        assert info["has_color"] is True
        assert "bounding_box" in info
        assert info["file_size"] > 0
    
    def test_voxel_downsample(self, temp_ply_file):
        """测试体素下采样"""
        processor = PointCloudProcessor(temp_ply_file)
        
        result = processor.voxel_downsample(voxel_size=0.5)
        
        assert result is not None
        assert len(result.points) < 1000  # 点数应该减少
        assert result.has_colors()
    
    def test_statistical_outlier_removal(self, temp_ply_file):
        """测试统计离群点移除"""
        processor = PointCloudProcessor(temp_ply_file)
        
        result = processor.statistical_outlier_removal(
            nb_neighbors=20,
            std_ratio=2.0
        )
        
        assert result is not None
        # 应该移除一些离群点
        assert len(result.points) <= 1000
    
    def test_ransac_plane_segmentation(self, temp_ply_file):
        """测试RANSAC平面分割"""
        processor = PointCloudProcessor(temp_ply_file)
        
        inliers, plane_model = processor.ransac_plane_segmentation(
            distance_threshold=0.05,
            num_iterations=1000
        )
        
        assert inliers is not None
        assert plane_model is not None
        assert len(plane_model) == 4  # [a, b, c, d] for plane equation ax+by+cz+d=0
        # 大部分点应该在平面上
        assert len(inliers) > 800
    
    def test_icp_registration(self, temp_ply_file):
        """测试ICP配准"""
        processor = PointCloudProcessor(temp_ply_file)
        source = processor.load()
        
        # 创建目标点云（对源点云进行变换）
        target = source.copy()
        target = target.translate([0.1, 0.1, 0.1])
        target = target.rotate(target.get_rotation_matrix_from_xyz([0.1, 0.1, 0.1]))
        
        # 保存目标点云到临时文件
        with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as f:
            target_path = f.name
        o3d.io.write_point_cloud(target_path, target)
        
        try:
            result = processor.icp_registration(
                target_path,
                max_correspondence_distance=0.5,
                max_iterations=50
            )
            
            assert result is not None
            assert "fitness" in result
            assert "inlier_rmse" in result
            assert "transformation" in result
            assert result["fitness"] > 0.5  # 应该有较好的配准效果
        finally:
            if os.path.exists(target_path):
                os.remove(target_path)
    
    def test_save_ply(self, temp_ply_file):
        """测试保存为PLY格式"""
        processor = PointCloudProcessor(temp_ply_file)
        pcd = processor.load()
        
        with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as f:
            output_path = f.name
        
        try:
            processor.save(pcd, output_path, 'ply')
            assert os.path.exists(output_path)
            
            # 验证可以重新加载
            loaded = o3d.io.read_point_cloud(output_path)
            assert len(loaded.points) == len(pcd.points)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)
    
    def test_save_obj(self, temp_ply_file):
        """测试保存为OBJ格式"""
        processor = PointCloudProcessor(temp_ply_file)
        pcd = processor.load()
        
        with tempfile.NamedTemporaryFile(suffix='.obj', delete=False) as f:
            output_path = f.name
        
        try:
            processor.save(pcd, output_path, 'obj')
            assert os.path.exists(output_path)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)
    
    def test_estimate_normals(self, temp_ply_file):
        """测试法线估计"""
        processor = PointCloudProcessor(temp_ply_file)
        pcd = processor.load()
        
        # 确保没有法线
        pcd.normals = o3d.utility.Vector3dVector(np.zeros((len(pcd.points), 3)))
        
        processor.estimate_normals(knn=10)
        
        assert processor.point_cloud.has_normals()
        # 法线应该被归一化
        normals = np.asarray(processor.point_cloud.normals)
        norms = np.linalg.norm(normals, axis=1)
        assert np.allclose(norms, 1.0, atol=0.01)
    
    def test_crop(self, temp_ply_file):
        """测试裁剪"""
        processor = PointCloudProcessor(temp_ply_file)
        
        # 裁剪中心区域
        result = processor.crop(
            min_bound=[-2, -2, -1],
            max_bound=[2, 2, 1]
        )
        
        assert result is not None
        assert len(result.points) < 1000  # 点数应该减少
    
    def test_preprocess(self, temp_ply_file):
        """测试预处理"""
        processor = PointCloudProcessor(temp_ply_file)
        
        result = processor.preprocess(
            voxel_size=0.5,
            remove_outliers=True
        )
        
        assert result is not None
        assert len(result.points) <= 1000
    
    def test_empty_pointcloud(self):
        """测试空点云处理"""
        # 创建空点云
        pcd = o3d.geometry.PointCloud()
        
        with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as f:
            temp_path = f.name
        
        o3d.io.write_point_cloud(temp_path, pcd)
        
        try:
            processor = PointCloudProcessor(temp_path)
            info = processor.get_info()
            
            assert info["point_count"] == 0
            
            # 处理空点云应该返回空
            result = processor.voxel_downsample(0.1)
            assert result is None or len(result.points) == 0
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_invalid_file(self):
        """测试无效文件"""
        with pytest.raises(Exception):
            processor = PointCloudProcessor("/nonexistent/file.ply")
            processor.load()


class TestLargePointCloud:
    """大点云处理测试"""
    
    def test_large_pointcloud_processing(self):
        """测试大点云处理性能"""
        # 创建100万点的点云
        np.random.seed(42)
        points = np.random.randn(1000000, 3)
        
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        
        with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as f:
            temp_path = f.name
        
        o3d.io.write_point_cloud(temp_path, pcd)
        
        try:
            import time
            
            processor = PointCloudProcessor(temp_path)
            
            # 测试加载时间
            start = time.time()
            loaded = processor.load()
            load_time = time.time() - start
            
            assert len(loaded.points) == 1000000
            assert load_time < 30  # 加载应在30秒内完成
            
            # 测试下采样时间
            start = time.time()
            result = processor.voxel_downsample(voxel_size=0.1)
            process_time = time.time() - start
            
            assert result is not None
            assert process_time < 60  # 处理应在60秒内完成
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
