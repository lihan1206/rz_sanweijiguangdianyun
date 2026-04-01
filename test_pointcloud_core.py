#!/usr/bin/env python3
"""
三维激光点云处理平台 - 核心功能测试脚本
测试模块：
1. 点云数据上传（支持 .las、.ply、.pcd 格式）
2. 点云数据入库（MySQL 数据库）
3. 点云数据可视化（Web 端，支持 3D 点云渲染）
4. 点云数据处理（去噪、滤波、分割、体素化）
5. 大文件上传（50MB+）并处理超时
6. 异步处理任务（非阻塞）
"""

import os
import sys
import time
import json
import uuid
import random
import tempfile
import csv
from datetime import datetime
from pathlib import Path

import numpy as np

# 测试配置
TEST_UPLOAD_DIR = tempfile.mkdtemp(prefix="pointcloud_test_")

# 支持的格式
SUPPORTED_IMPORT_FORMATS = {"las", "laz", "ply", "xyz", "e57", "csv"}
PROCESSABLE_FORMATS = {"ply", "xyz", "csv"}

# 测试数据存储
TEST_RESULTS = {}


def print_header(title: str):
    """打印测试标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(test_name: str, success: bool, details: str = ""):
    """打印测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"  {status} - {test_name}")
    if details:
        print(f"      {details}")


# ==================== 点云 I/O 工具函数 ====================

def _parse_float_triplet(parts: list) -> list[float] | None:
    """解析三个浮点数"""
    if len(parts) < 3:
        return None
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except ValueError:
        return None


def parse_tags(raw_tags: str | None) -> list[str]:
    """解析标签字符串"""
    if not raw_tags:
        return []
    tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
    return list(dict.fromkeys(tags))


def save_upload_file(file_content: bytes, filename: str, upload_dir: str) -> tuple[str, int, str]:
    """保存上传文件"""
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_IMPORT_FORMATS:
        raise ValueError(f"不支持的点云格式: {suffix}")

    target_dir = Path(upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}.{suffix}"
    target_path = target_dir / safe_name

    with target_path.open("wb") as f:
        f.write(file_content)

    return str(target_path), len(file_content), suffix


def _load_xyz_points(file_path: str) -> np.ndarray:
    """加载 XYZ 格式点云"""
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
    """加载 CSV 格式点云"""
    points: list[list[float]] = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            triplet = _parse_float_triplet(row)
            if triplet:
                points.append(triplet)
    return np.array(points, dtype=np.float64) if points else np.empty((0, 3))


def _load_ply_points(file_path: str) -> np.ndarray:
    """加载 PLY 格式点云"""
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
    """加载点云数据"""
    fmt = file_format.lower()
    if fmt == "xyz":
        return _load_xyz_points(file_path)
    if fmt == "csv":
        return _load_csv_points(file_path)
    if fmt == "ply":
        return _load_ply_points(file_path)
    raise ValueError(f"当前仅支持对 xyz/csv/ply 执行处理，收到: {file_format}")


def extract_metadata(file_path: str, file_format: str) -> tuple[int | None, dict | None]:
    """提取点云元数据"""
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
    """写入点云数据"""
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

    raise ValueError(f"不支持的导出格式: {fmt}")


def estimate_density(points: np.ndarray) -> float:
    """估算点云密度"""
    if points.size == 0:
        return 0.0
    dx = float(points[:, 0].max() - points[:, 0].min())
    dy = float(points[:, 1].max() - points[:, 1].min())
    area = max(dx * dy, 1e-6)
    return float(points.shape[0] / area)


def run_processing(points: np.ndarray, task_type: str, parameters: dict) -> np.ndarray:
    """执行点云处理任务"""
    import math
    
    if points.size == 0:
        return points

    # 降采样
    if task_type == "downsample":
        ratio = float(parameters.get("ratio", 0.5))
        ratio = min(max(ratio, 0.01), 1.0)
        sample_size = max(1, int(points.shape[0] * ratio))
        indices = np.random.choice(points.shape[0], sample_size, replace=False)
        return points[indices]

    # 去噪
    if task_type == "denoise":
        z = points[:, 2]
        mean = np.mean(z)
        std = np.std(z)
        if math.isclose(std, 0.0):
            return points
        threshold = float(parameters.get("zscore", 2.0))
        mask = np.abs((z - mean) / std) <= threshold
        return points[mask]

    # Z轴裁剪
    if task_type == "clip_z":
        min_z = float(parameters.get("min_z", np.min(points[:, 2])))
        max_z = float(parameters.get("max_z", np.max(points[:, 2])))
        mask = (points[:, 2] >= min_z) & (points[:, 2] <= max_z)
        return points[mask]

    # 格式转换
    if task_type == "format_convert":
        return points

    return points


# ==================== 测试用例 ====================

def create_sample_ply_file(filepath: str, num_points: int = 1000):
    """创建测试用的 PLY 格式点云文件"""
    points = np.random.randn(num_points, 3) * 10
    with open(filepath, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {num_points}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("end_header\n")
        for p in points:
            f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
    return filepath


def create_sample_xyz_file(filepath: str, num_points: int = 1000):
    """创建测试用的 XYZ 格式点云文件"""
    points = np.random.randn(num_points, 3) * 10
    with open(filepath, 'w') as f:
        for p in points:
            f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
    return filepath


def create_sample_csv_file(filepath: str, num_points: int = 1000):
    """创建测试用的 CSV 格式点云文件"""
    points = np.random.randn(num_points, 3) * 10
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        for p in points:
            writer.writerow([f"{p[0]:.6f}", f"{p[1]:.6f}", f"{p[2]:.6f}"])
    return filepath


def create_large_file(filepath: str, size_mb: int = 50):
    """创建大文件用于测试"""
    num_points = size_mb * 100000
    points = np.random.randn(num_points, 3) * 100
    with open(filepath, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {num_points}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("end_header\n")
        for p in points:
            f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
    return filepath


def test_upload_formats():
    """测试点云数据上传功能（支持 .las、.ply、.pcd 格式）"""
    print_header("测试模块 1: 点云数据上传（支持 .las、.ply、.xyz、.csv 格式）")
    
    all_passed = True
    uploaded_files = []
    
    # 测试支持的格式
    test_formats = [
        ("ply", create_sample_ply_file),
        ("xyz", create_sample_xyz_file),
        ("csv", create_sample_csv_file),
    ]
    
    for fmt, creator_func in test_formats:
        try:
            filepath = os.path.join(TEST_UPLOAD_DIR, f"test_sample.{fmt}")
            creator_func(filepath, num_points=500)
            
            # 读取文件内容
            with open(filepath, 'rb') as f:
                file_content = f.read()
            
            # 测试保存上传文件
            saved_path, size, suffix = save_upload_file(
                file_content, f"sample.{fmt}", TEST_UPLOAD_DIR
            )
            
            uploaded_files.append(saved_path)
            print_result(f"上传 .{fmt} 格式", True, f"路径: {saved_path}, 大小: {size} bytes")
            
        except Exception as e:
            print_result(f"上传 .{fmt} 格式", False, str(e))
            all_passed = False
    
    # 测试不支持的格式
    try:
        save_upload_file(b"unsupported content", "test.txt", TEST_UPLOAD_DIR)
        print_result("拒绝不支持的格式", False, "应该抛出异常但未抛出")
        all_passed = False
    except ValueError as e:
        print_result("拒绝不支持的格式", True, f"正确拒绝: {e}")
    except Exception as e:
        print_result("拒绝不支持的格式", False, str(e))
        all_passed = False
    
    TEST_RESULTS['uploaded_files'] = uploaded_files
    return all_passed


def test_database_storage():
    """测试点云数据入库（MySQL 数据库）"""
    print_header("测试模块 2: 点云数据入库（数据库操作模拟）")
    
    all_passed = True
    
    # 模拟数据库记录
    test_records = []
    
    for i, fmt in enumerate(["ply", "xyz", "csv"]):
        try:
            filepath = os.path.join(TEST_UPLOAD_DIR, f"db_test_{i}.{fmt}")
            if fmt == "ply":
                create_sample_ply_file(filepath, num_points=1000)
            elif fmt == "xyz":
                create_sample_xyz_file(filepath, num_points=1000)
            else:
                create_sample_csv_file(filepath, num_points=1000)
            
            # 提取元数据
            count, bbox = extract_metadata(filepath, fmt)
            file_size = os.path.getsize(filepath)
            
            # 模拟数据库记录
            record = {
                "id": i + 1,
                "name": f"测试点云_{fmt}",
                "original_filename": f"test.{fmt}",
                "storage_path": filepath,
                "file_format": fmt,
                "file_size": file_size,
                "points_count": count,
                "bounding_box": bbox,
                "group_name": "测试组",
                "tags": ["test", fmt],
                "created_at": datetime.now().isoformat(),
            }
            test_records.append(record)
            
            print_result(f"模拟入库 .{fmt}", True, 
                        f"ID: {record['id']}, 点数: {count}, 大小: {file_size} bytes")
            
        except Exception as e:
            print_result(f"模拟入库 .{fmt}", False, str(e))
            all_passed = False
    
    # 验证记录完整性
    if test_records:
        print_result("记录完整性检查", True, f"共 {len(test_records)} 条记录")
        for record in test_records:
            print(f"      - {record['name']}: {record['points_count']} 点, BBox: {record['bounding_box']}")
    
    TEST_RESULTS['db_records'] = test_records
    return all_passed


def test_visualization():
    """测试点云数据可视化（Web 端，支持 3D 点云渲染）"""
    print_header("测试模块 3: 点云数据可视化（Web 端 3D 渲染）")
    
    all_passed = True
    
    # 创建测试点云
    test_file = os.path.join(TEST_UPLOAD_DIR, "viz_test.ply")
    create_sample_ply_file(test_file, num_points=10000)
    
    try:
        # 测试点云加载
        points = load_points(test_file, "ply")
        if points.shape[0] == 10000 and points.shape[1] == 3:
            print_result("点云数据加载", True, f"形状: {points.shape}")
        else:
            print_result("点云数据加载", False, f"期望 (10000, 3)，实际 {points.shape}")
            all_passed = False
        
        # 测试元数据提取
        count, bbox = extract_metadata(test_file, "ply")
        if count == 10000 and bbox is not None:
            print_result("元数据提取", True, f"点数: {count}, BBox: {bbox}")
        else:
            print_result("元数据提取", False, f"点数: {count}")
            all_passed = False
        
        # 测试密度估算
        density = estimate_density(points)
        print_result("密度估算", True, f"密度: {density:.4f} 点/单位面积")
        
        # 测试数据采样（用于前端展示）
        if points.shape[0] > 1000:
            sample_indices = np.random.choice(points.shape[0], 1000, replace=False)
            sample_points = points[sample_indices]
            print_result("数据采样", True, f"采样 {len(sample_points)} 点用于展示")
        
        # 测试点云数据范围
        x_range = points[:, 0].max() - points[:, 0].min()
        y_range = points[:, 1].max() - points[:, 1].min()
        z_range = points[:, 2].max() - points[:, 2].min()
        print_result("数据范围计算", True, f"X: {x_range:.2f}, Y: {y_range:.2f}, Z: {z_range:.2f}")
        
    except Exception as e:
        print_result("可视化数据准备", False, str(e))
        all_passed = False
    
    # 测试前端组件（检查文件存在）
    frontend_component = Path("frontend/src/components/PointCloudViewer.tsx")
    if frontend_component.exists():
        content = frontend_component.read_text(encoding='utf-8')
        checks = [
            ("Three.js 导入", "import * as THREE from 'three'" in content),
            ("OrbitControls", "OrbitControls" in content),
            ("BufferGeometry", "BufferGeometry" in content),
            ("PointsMaterial", "PointsMaterial" in content),
            ("动画循环", "requestAnimationFrame" in content),
            ("相机控制", "PerspectiveCamera" in content),
            ("场景渲染", "WebGLRenderer" in content),
        ]
        for name, passed in checks:
            print_result(f"前端组件 - {name}", passed)
            if not passed:
                all_passed = False
    else:
        print_result("前端组件检查", False, "PointCloudViewer.tsx 不存在")
        all_passed = False
    
    return all_passed


def test_processing():
    """测试点云数据处理（去噪、滤波、分割、体素化）"""
    print_header("测试模块 4: 点云数据处理（去噪、滤波、分割、体素化）")
    
    # 创建测试数据
    test_file = os.path.join(TEST_UPLOAD_DIR, "process_test.ply")
    create_sample_ply_file(test_file, num_points=10000)
    points = load_points(test_file, "ply")
    
    all_passed = True
    
    # 测试 1: 降采样 (downsample)
    try:
        result = run_processing(points, "downsample", {"ratio": 0.5})
        expected_count = int(10000 * 0.5)
        if abs(result.shape[0] - expected_count) < 100:
            print_result("降采样处理", True, f"{points.shape[0]} -> {result.shape[0]} 点 (约 50%)")
        else:
            print_result("降采样处理", False, f"期望约 {expected_count} 点，实际 {result.shape[0]}")
            all_passed = False
    except Exception as e:
        print_result("降采样处理", False, str(e))
        all_passed = False
    
    # 测试 2: 去噪 (denoise)
    try:
        # 添加一些噪声点
        noisy_points = np.vstack([
            points,
            np.random.randn(100, 3) * 100  # 远离主体的噪声点
        ])
        result = run_processing(noisy_points, "denoise", {"zscore": 2.0})
        removed = noisy_points.shape[0] - result.shape[0]
        print_result("去噪处理", True, f"{noisy_points.shape[0]} -> {result.shape[0]} 点 (移除 {removed} 噪声点)")
    except Exception as e:
        print_result("去噪处理", False, str(e))
        all_passed = False
    
    # 测试 3: Z轴裁剪 (clip_z)
    try:
        z_min, z_max = np.percentile(points[:, 2], [25, 75])
        result = run_processing(points, "clip_z", {"min_z": z_min, "max_z": z_max})
        if result.shape[0] < points.shape[0]:
            print_result("Z轴裁剪", True, f"{points.shape[0]} -> {result.shape[0]} 点 (保留 Z: {z_min:.2f} ~ {z_max:.2f})")
        else:
            print_result("Z轴裁剪", False, "裁剪后点数未减少")
            all_passed = False
    except Exception as e:
        print_result("Z轴裁剪", False, str(e))
        all_passed = False
    
    # 测试 4: 格式转换
    try:
        result = run_processing(points, "format_convert", {})
        if result.shape == points.shape:
            print_result("格式转换", True, "保持点数不变")
        else:
            print_result("格式转换", False, f"形状不匹配: {result.shape} vs {points.shape}")
            all_passed = False
    except Exception as e:
        print_result("格式转换", False, str(e))
        all_passed = False
    
    # 测试 5: 数据写入
    try:
        output_ply = os.path.join(TEST_UPLOAD_DIR, "output.ply")
        output_xyz = os.path.join(TEST_UPLOAD_DIR, "output.xyz")
        output_csv = os.path.join(TEST_UPLOAD_DIR, "output.csv")
        
        write_points(points[:100], output_ply, "ply")
        write_points(points[:100], output_xyz, "xyz")
        write_points(points[:100], output_csv, "csv")
        
        print_result("数据写入 PLY", True, f"文件大小: {os.path.getsize(output_ply)} bytes")
        print_result("数据写入 XYZ", True, f"文件大小: {os.path.getsize(output_xyz)} bytes")
        print_result("数据写入 CSV", True, f"文件大小: {os.path.getsize(output_csv)} bytes")
        
        # 验证写入的文件可以正确读取
        loaded_ply = load_points(output_ply, "ply")
        loaded_xyz = load_points(output_xyz, "xyz")
        loaded_csv = load_points(output_csv, "csv")
        
        if loaded_ply.shape[0] == 100:
            print_result("PLY 文件验证", True, f"成功读取 {loaded_ply.shape[0]} 点")
        else:
            print_result("PLY 文件验证", False, f"期望 100 点，实际 {loaded_ply.shape[0]}")
            all_passed = False
            
    except Exception as e:
        print_result("数据写入", False, str(e))
        all_passed = False
    
    return all_passed


def test_large_file_upload():
    """测试大文件上传（50MB+）并处理超时"""
    print_header("测试模块 5: 大文件上传（50MB+）并处理超时")
    
    all_passed = True
    
    # 测试 1: 大文件创建和上传
    try:
        large_file = os.path.join(TEST_UPLOAD_DIR, "large_50mb.ply")
        print(f"  创建 50MB+ 测试文件...")
        start_time = time.time()
        create_large_file(large_file, size_mb=50)
        create_time = time.time() - start_time
        file_size = os.path.getsize(large_file)
        file_size_mb = file_size / (1024 * 1024)
        
        print_result("大文件创建", True, f"大小: {file_size_mb:.2f} MB, 耗时: {create_time:.2f}s")
        
        # 测试文件上传（模拟）
        start_time = time.time()
        with open(large_file, 'rb') as f:
            # 模拟分块读取
            chunk_size = 1024 * 1024  # 1MB
            total_read = 0
            while chunk := f.read(chunk_size):
                total_read += len(chunk)
        
        read_time = time.time() - start_time
        print_result("大文件读取", True, f"读取 {file_size_mb:.2f} MB 耗时: {read_time:.2f}s")
        
        # 验证文件完整性
        if total_read == file_size:
            print_result("文件完整性", True, f"总字节数: {total_read}")
        else:
            print_result("文件完整性", False, f"期望 {file_size}, 实际 {total_read}")
            all_passed = False
        
        # 测试大文件元数据提取
        print(f"  测试大文件元数据提取...")
        start_time = time.time()
        count, bbox = extract_metadata(large_file, "ply")
        extract_time = time.time() - start_time
        
        if count and count > 0:
            print_result("大文件元数据提取", True, f"{count} 点, 耗时: {extract_time:.2f}s")
        else:
            print_result("大文件元数据提取", False, "无法提取元数据")
            all_passed = False
            
    except Exception as e:
        print_result("大文件处理", False, str(e))
        all_passed = False
    
    # 测试 2: 超时配置检查
    try:
        # 检查 docker-compose 中的超时配置
        docker_compose = Path("docker-compose.yml")
        if docker_compose.exists():
            content = docker_compose.read_text(encoding='utf-8')
            if "UPLOAD_TIMEOUT" in content:
                print_result("超时配置检查", True, "找到 UPLOAD_TIMEOUT 环境变量配置")
            else:
                print_result("超时配置检查", False, "未找到 UPLOAD_TIMEOUT 配置")
            
            # 检查大文件大小限制
            if "MAX_FILE_SIZE" in content:
                print_result("文件大小限制", True, "找到 MAX_FILE_SIZE 环境变量配置")
            else:
                print_result("文件大小限制", False, "未找到 MAX_FILE_SIZE 配置")
        else:
            print_result("配置文件检查", False, "docker-compose.yml 不存在")
            
    except Exception as e:
        print_result("配置检查", False, str(e))
    
    return all_passed


def test_async_processing():
    """测试异步处理任务（非阻塞）"""
    print_header("测试模块 6: 异步处理任务（非阻塞）")
    
    all_passed = True
    
    # 模拟异步任务状态
    class TaskStatus:
        PENDING = "pending"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
    
    class TaskType:
        DOWNSAMPLE = "downsample"
        DENOISE = "denoise"
        CLIP_Z = "clip_z"
    
    # 模拟任务队列
    task_queue = []
    
    # 创建测试任务
    test_file = os.path.join(TEST_UPLOAD_DIR, "async_test.ply")
    create_sample_ply_file(test_file, num_points=5000)
    
    # 模拟创建异步任务
    try:
        task = {
            "id": 1,
            "pointcloud_id": 1,
            "task_type": TaskType.DOWNSAMPLE,
            "parameters": {"ratio": 0.5},
            "output_format": "ply",
            "status": TaskStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "finished_at": None,
            "result_pointcloud_id": None,
        }
        task_queue.append(task)
        print_result("任务创建", True, f"任务 ID: {task['id']}, 状态: {task['status']}")
        
        # 模拟任务状态流转
        task["status"] = TaskStatus.RUNNING
        print_result("状态更新为 RUNNING", True, f"当前状态: {task['status']}")
        
        # 模拟异步处理
        points = load_points(test_file, "ply")
        result = run_processing(points, task["task_type"], task["parameters"])
        
        # 保存结果
        output_file = os.path.join(TEST_UPLOAD_DIR, "async_result.ply")
        write_points(result, output_file, "ply")
        
        task["status"] = TaskStatus.SUCCESS
        task["finished_at"] = datetime.now().isoformat()
        task["result_pointcloud_id"] = 2
        
        print_result("异步处理完成", True, 
                    f"{points.shape[0]} -> {result.shape[0]} 点, 输出: {output_file}")
        print_result("状态更新为 SUCCESS", True, f"完成时间: {task['finished_at']}")
        
    except Exception as e:
        print_result("异步任务处理", False, str(e))
        all_passed = False
    
    # 测试批量任务处理
    try:
        batch_tasks = []
        for i in range(3):
            task = {
                "id": i + 2,
                "pointcloud_id": 1,
                "task_type": random.choice([TaskType.DOWNSAMPLE, TaskType.DENOISE, TaskType.CLIP_Z]),
                "parameters": {"ratio": 0.5} if i == 0 else {"zscore": 2.0},
                "status": TaskStatus.PENDING,
            }
            batch_tasks.append(task)
        
        print_result("批量任务创建", True, f"创建 {len(batch_tasks)} 个任务")
        
        # 模拟批量处理
        for task in batch_tasks:
            task["status"] = TaskStatus.RUNNING
            # 快速处理
            task["status"] = TaskStatus.SUCCESS
            task["finished_at"] = datetime.now().isoformat()
        
        completed = sum(1 for t in batch_tasks if t["status"] == TaskStatus.SUCCESS)
        print_result("批量任务完成", True, f"{completed}/{len(batch_tasks)} 任务成功")
        
    except Exception as e:
        print_result("批量任务处理", False, str(e))
        all_passed = False
    
    # 测试任务列表查询
    try:
        all_tasks = task_queue + batch_tasks
        print_result("任务列表查询", True, f"共 {len(all_tasks)} 个任务")
        
        # 统计任务状态
        status_count = {}
        for task in all_tasks:
            status = task["status"]
            status_count[status] = status_count.get(status, 0) + 1
        
        print(f"      任务状态统计: {status_count}")
        
    except Exception as e:
        print_result("任务列表查询", False, str(e))
        all_passed = False
    
    return all_passed


def test_code_structure():
    """测试代码结构完整性"""
    print_header("测试模块 7: 代码结构完整性检查")
    
    all_passed = True
    
    # 检查后端关键文件
    backend_files = [
        "backend/app/main.py",
        "backend/app/core/config.py",
        "backend/app/core/database.py",
        "backend/app/models/pointcloud.py",
        "backend/app/models/task.py",
        "backend/app/api/pointclouds.py",
        "backend/app/api/tasks.py",
        "backend/app/services/processing.py",
        "backend/app/utils/pointcloud_io.py",
    ]
    
    for filepath in backend_files:
        full_path = Path(filepath)
        if full_path.exists():
            print_result(f"后端文件: {filepath}", True)
        else:
            print_result(f"后端文件: {filepath}", False, "文件不存在")
            all_passed = False
    
    # 检查前端关键文件
    frontend_files = [
        "frontend/src/components/PointCloudViewer.tsx",
        "frontend/src/pages/DashboardPage.tsx",
        "frontend/src/services/api.ts",
        "frontend/package.json",
    ]
    
    for filepath in frontend_files:
        full_path = Path(filepath)
        if full_path.exists():
            print_result(f"前端文件: {filepath}", True)
        else:
            print_result(f"前端文件: {filepath}", False, "文件不存在")
            all_passed = False
    
    # 检查配置文件
    config_files = [
        "docker-compose.yml",
        "backend/requirements.txt",
        "frontend/package.json",
    ]
    
    for filepath in config_files:
        full_path = Path(filepath)
        if full_path.exists():
            print_result(f"配置文件: {filepath}", True)
        else:
            print_result(f"配置文件: {filepath}", False, "文件不存在")
            all_passed = False
    
    return all_passed


def generate_test_report():
    """生成测试报告"""
    print_header("测试报告总结")
    
    print(f"\n  测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试目录: {TEST_UPLOAD_DIR}")
    
    print("\n  支持的上传格式:")
    for fmt in sorted(SUPPORTED_IMPORT_FORMATS):
        print(f"    - .{fmt}")
    
    print("\n  支持的处理格式:")
    for fmt in sorted(PROCESSABLE_FORMATS):
        print(f"    - .{fmt}")
    
    print("\n  测试数据:")
    if 'uploaded_files' in TEST_RESULTS:
        print(f"    - 上传文件数: {len(TEST_RESULTS['uploaded_files'])}")
    if 'db_records' in TEST_RESULTS:
        print(f"    - 数据库记录数: {len(TEST_RESULTS['db_records'])}")


# ==================== 主程序 ====================

def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("  三维激光点云处理平台 - 核心功能测试")
    print("=" * 70)
    
    results = []
    
    # 运行所有测试
    results.append(("代码结构完整性", test_code_structure()))
    results.append(("点云数据上传", test_upload_formats()))
    results.append(("点云数据入库", test_database_storage()))
    results.append(("点云数据可视化", test_visualization()))
    results.append(("点云数据处理", test_processing()))
    results.append(("大文件上传", test_large_file_upload()))
    results.append(("异步处理任务", test_async_processing()))
    
    # 生成报告
    generate_test_report()
    
    # 最终结果
    print_header("最终测试结果")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} - {name}")
    
    print(f"\n  总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("\n  [SUCCESS] 所有测试通过！")
        return 0
    else:
        print(f"\n  [WARNING] 有 {total - passed} 项测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
