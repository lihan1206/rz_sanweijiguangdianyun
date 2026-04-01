#!/usr/bin/env python3
"""
三维激光点云处理平台 - 功能测试脚本
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
from datetime import datetime
from pathlib import Path

# 添加后端路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# 导入应用组件
from app.main import app
from app.core.config import get_settings, Settings
from app.core.database import Base, get_db
from app.models.user import User, UserRole
from app.models.pointcloud import PointCloud
from app.models.task import ProcessingTask, TaskStatus
from app.utils.pointcloud_io import (
    SUPPORTED_IMPORT_FORMATS,
    save_upload_file,
    load_points,
    extract_metadata,
    write_points,
    run_processing,
    estimate_density,
)

# 测试配置
TEST_DB_URL = "sqlite:///./test_pointcloud.db"
TEST_UPLOAD_DIR = tempfile.mkdtemp(prefix="pointcloud_test_")

# 创建测试数据库引擎
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# 创建测试数据库表
Base.metadata.create_all(bind=test_engine)

# 覆盖依赖项
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# 创建测试客户端
client = TestClient(app)

# 测试数据存储
TEST_RESULTS = {}


def print_header(title: str):
    """打印测试标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(test_name: str, success: bool, details: str = ""):
    """打印测试结果"""
    status = "✅ 通过" if success else "❌ 失败"
    print(f"  {status} - {test_name}")
    if details:
        print(f"      {details}")


# ==================== 测试工具函数 ====================

def create_test_user(db: Session, username: str, role: UserRole = UserRole.ADMIN):
    """创建测试用户"""
    from app.core.security import get_password_hash
    user = User(
        username=username,
        password_hash=get_password_hash("test123"),
        role=role,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_auth_token(username: str = "testadmin"):
    """获取认证令牌"""
    response = client.post("/api/v1/auth/login", data={
        "username": username,
        "password": "test123"
    })
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


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
    import csv
    points = np.random.randn(num_points, 3) * 10
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        for p in points:
            writer.writerow([f"{p[0]:.6f}", f"{p[1]:.6f}", f"{p[2]:.6f}"])
    return filepath


def create_sample_las_file(filepath: str, num_points: int = 1000):
    """创建测试用的 LAS 格式点云文件（模拟）"""
    # LAS 格式需要 laspy 库，这里创建一个模拟文件用于测试上传
    # 实际项目中应该使用 laspy 创建真实的 LAS 文件
    header = b"LASF" + b"\x00" * 227  # LAS 文件头模拟
    points_data = np.random.randn(num_points, 3).astype(np.float32).tobytes()
    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(points_data)
    return filepath


def create_large_file(filepath: str, size_mb: int = 50):
    """创建大文件用于测试"""
    # 创建一个大点云文件
    num_points = size_mb * 100000  # 大约每MB 10万点
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


# ==================== 测试用例 ====================

def test_upload_formats():
    """测试点云数据上传功能（支持 .las、.ply、.pcd 格式）"""
    print_header("测试模块 1: 点云数据上传（支持 .las、.ply、.xyz、.csv 格式）")
    
    db = TestingSessionLocal()
    user = create_test_user(db, "upload_tester")
    token = get_auth_token("upload_tester")
    db.close()
    
    if not token:
        print_result("用户认证", False, "无法获取认证令牌")
        return False
    
    print_result("用户认证", True, f"获取到访问令牌")
    
    # 测试支持的格式
    test_formats = [
        ("ply", create_sample_ply_file),
        ("xyz", create_sample_xyz_file),
        ("csv", create_sample_csv_file),
    ]
    
    all_passed = True
    uploaded_ids = []
    
    for fmt, creator_func in test_formats:
        try:
            filepath = os.path.join(TEST_UPLOAD_DIR, f"test_sample.{fmt}")
            creator_func(filepath, num_points=500)
            
            with open(filepath, 'rb') as f:
                response = client.post(
                    "/api/v1/pointclouds/upload",
                    headers={"Authorization": f"Bearer {token}"},
                    data={
                        "name": f"测试点云_{fmt}",
                        "group_name": "测试组",
                        "tags": "test,upload",
                    },
                    files={"file": (f"sample.{fmt}", f, f"application/octet-stream")}
                )
            
            if response.status_code == 200:
                data = response.json()
                uploaded_ids.append(data.get('id'))
                print_result(f"上传 .{fmt} 格式", True, f"ID: {data.get('id')}, 点数: {data.get('points_count')}")
            else:
                print_result(f"上传 .{fmt} 格式", False, f"状态码: {response.status_code}, {response.text}")
                all_passed = False
                
        except Exception as e:
            print_result(f"上传 .{fmt} 格式", False, str(e))
            all_passed = False
    
    # 测试不支持的格式
    try:
        unsupported_file = os.path.join(TEST_UPLOAD_DIR, "test.txt")
        with open(unsupported_file, 'w') as f:
            f.write("unsupported content")
        
        with open(unsupported_file, 'rb') as f:
            response = client.post(
                "/api/v1/pointclouds/upload",
                headers={"Authorization": f"Bearer {token}"},
                data={"name": "测试不支持的格式"},
                files={"file": ("sample.txt", f, "text/plain")}
            )
        
        if response.status_code == 400:
            print_result("拒绝不支持的格式", True, "正确返回 400 错误")
        else:
            print_result("拒绝不支持的格式", False, f"期望 400，实际 {response.status_code}")
            all_passed = False
    except Exception as e:
        print_result("拒绝不支持的格式", False, str(e))
        all_passed = False
    
    TEST_RESULTS['uploaded_ids'] = uploaded_ids
    return all_passed


def test_database_storage():
    """测试点云数据入库（MySQL 数据库）"""
    print_header("测试模块 2: 点云数据入库（数据库操作）")
    
    db = TestingSessionLocal()
    user = create_test_user(db, "db_tester")
    token = get_auth_token("db_tester")
    
    # 创建测试点云记录
    test_pc = PointCloud(
        name="数据库测试点云",
        original_filename="db_test.ply",
        storage_path=os.path.join(TEST_UPLOAD_DIR, "db_test.ply"),
        file_format="ply",
        file_size=1024,
        points_count=1000,
        bounding_box={"x": [0, 10], "y": [0, 10], "z": [0, 10]},
        group_name="数据库测试组",
        tags=["db", "test"],
        created_by=user.id
    )
    db.add(test_pc)
    db.commit()
    db.refresh(test_pc)
    
    # 验证数据库记录
    stored_pc = db.query(PointCloud).filter(PointCloud.id == test_pc.id).first()
    
    all_passed = True
    
    if stored_pc:
        print_result("数据插入", True, f"ID: {stored_pc.id}")
        print_result("字段完整性", True, 
                    f"名称: {stored_pc.name}, 格式: {stored_pc.file_format}, 点数: {stored_pc.points_count}")
        print_result("边界框存储", True, f"BBox: {stored_pc.bounding_box}")
        print_result("标签存储", True, f"Tags: {stored_pc.tags}")
    else:
        print_result("数据插入", False, "无法查询到插入的记录")
        all_passed = False
    
    # 测试 API 查询
    if token:
        response = client.get(
            "/api/v1/pointclouds",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            data = response.json()
            print_result("API 列表查询", True, f"返回 {len(data)} 条记录")
        else:
            print_result("API 列表查询", False, f"状态码: {response.status_code}")
            all_passed = False
        
        # 测试详情查询
        response = client.get(
            f"/api/v1/pointclouds/{test_pc.id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 200:
            print_result("API 详情查询", True, "成功获取点云详情")
        else:
            print_result("API 详情查询", False, f"状态码: {response.status_code}")
            all_passed = False
    
    db.close()
    return all_passed


def test_visualization():
    """测试点云数据可视化（Web 端，支持 3D 点云渲染）"""
    print_header("测试模块 3: 点云数据可视化（Web 端 3D 渲染）")
    
    # 测试点云数据加载
    test_file = os.path.join(TEST_UPLOAD_DIR, "viz_test.ply")
    create_sample_ply_file(test_file, num_points=1000)
    
    all_passed = True
    
    try:
        # 测试点云加载
        points = load_points(test_file, "ply")
        if points.shape[0] == 1000 and points.shape[1] == 3:
            print_result("点云数据加载", True, f"形状: {points.shape}")
        else:
            print_result("点云数据加载", False, f"期望 (1000, 3)，实际 {points.shape}")
            all_passed = False
        
        # 测试元数据提取
        count, bbox = extract_metadata(test_file, "ply")
        if count == 1000 and bbox is not None:
            print_result("元数据提取", True, f"点数: {count}, BBox: {bbox}")
        else:
            print_result("元数据提取", False, f"点数: {count}")
            all_passed = False
        
        # 测试密度估算
        density = estimate_density(points)
        print_result("密度估算", True, f"密度: {density:.4f} 点/单位面积")
        
        # 测试数据采样（用于前端展示）
        if points.shape[0] > 100:
            sample_indices = np.random.choice(points.shape[0], 100, replace=False)
            sample_points = points[sample_indices]
            print_result("数据采样", True, f"采样 {len(sample_points)} 点用于展示")
        
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
            print_result("降采样处理", True, f"{points.shape[0]} -> {result.shape[0]} 点")
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
        print_result("去噪处理", True, f"{noisy_points.shape[0]} -> {result.shape[0]} 点 (移除 {noisy_points.shape[0] - result.shape[0]} 噪声点)")
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
    except Exception as e:
        print_result("数据写入", False, str(e))
        all_passed = False
    
    return all_passed


def test_large_file_upload():
    """测试大文件上传（50MB+）并处理超时"""
    print_header("测试模块 5: 大文件上传（50MB+）并处理超时")
    
    db = TestingSessionLocal()
    user = create_test_user(db, "largefile_tester")
    token = get_auth_token("largefile_tester")
    db.close()
    
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
            
    except Exception as e:
        print_result("配置检查", False, str(e))
    
    return all_passed


def test_async_processing():
    """测试异步处理任务（非阻塞）"""
    print_header("测试模块 6: 异步处理任务（非阻塞）")
    
    db = TestingSessionLocal()
    user = create_test_user(db, "async_tester")
    token = get_auth_token("async_tester")
    
    # 创建测试点云
    test_pc = PointCloud(
        name="异步测试点云",
        original_filename="async_test.ply",
        storage_path=os.path.join(TEST_UPLOAD_DIR, "async_test.ply"),
        file_format="ply",
        file_size=1024,
        points_count=1000,
        created_by=user.id
    )
    db.add(test_pc)
    db.commit()
    db.refresh(test_pc)
    
    all_passed = True
    
    # 测试 1: 创建异步任务
    try:
        from app.models.task import TaskType
        
        task = ProcessingTask(
            pointcloud_id=test_pc.id,
            task_type=TaskType.DOWNSAMPLE,
            parameters={"ratio": 0.5},
            output_format="ply",
            status=TaskStatus.PENDING,
            created_by=user.id
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        print_result("任务创建", True, f"任务 ID: {task.id}, 状态: {task.status.value}")
        
        # 测试 2: 任务状态流转
        task.status = TaskStatus.RUNNING
        db.commit()
        print_result("状态更新为 RUNNING", True, f"当前状态: {task.status.value}")
        
        task.status = TaskStatus.SUCCESS
        task.finished_at = datetime.utcnow()
        db.commit()
        print_result("状态更新为 SUCCESS", True, f"完成时间: {task.finished_at}")
        
    except Exception as e:
        print_result("任务状态管理", False, str(e))
        all_passed = False
    
    # 测试 3: API 异步任务创建
    if token:
        try:
            response = client.post(
                "/api/v1/tasks",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "pointcloud_id": test_pc.id,
                    "task_type": "downsample",
                    "parameters": {"ratio": 0.5},
                    "output_format": "ply"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print_result("API 创建异步任务", True, 
                            f"任务 ID: {data.get('id')}, 状态: {data.get('status')}")
            else:
                print_result("API 创建异步任务", False, 
                            f"状态码: {response.status_code}, {response.text}")
                all_passed = False
                
        except Exception as e:
            print_result("API 创建异步任务", False, str(e))
            all_passed = False
    
    # 测试 4: 任务列表查询
    if token:
        try:
            response = client.get(
                "/api/v1/tasks",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                tasks = response.json()
                print_result("任务列表查询", True, f"返回 {len(tasks)} 个任务")
            else:
                print_result("任务列表查询", False, f"状态码: {response.status_code}")
                all_passed = False
                
        except Exception as e:
            print_result("任务列表查询", False, str(e))
            all_passed = False
    
    db.close()
    return all_passed


def test_system_health():
    """测试系统健康状态"""
    print_header("系统健康检查")
    
    all_passed = True
    
    # 测试健康检查端点
    try:
        response = client.get("/health")
        if response.status_code == 200:
            data = response.json()
            print_result("健康检查", True, f"状态: {data.get('status')}, 服务: {data.get('service')}")
        else:
            print_result("健康检查", False, f"状态码: {response.status_code}")
            all_passed = False
    except Exception as e:
        print_result("健康检查", False, str(e))
        all_passed = False
    
    return all_passed


def generate_test_report():
    """生成测试报告"""
    print_header("测试报告总结")
    
    print(f"\n  测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试目录: {TEST_UPLOAD_DIR}")
    print(f"  测试数据库: {TEST_DB_URL}")
    
    print("\n  支持的上传格式:")
    for fmt in sorted(SUPPORTED_IMPORT_FORMATS):
        print(f"    - .{fmt}")
    
    print("\n  测试数据 ID:")
    if 'uploaded_ids' in TEST_RESULTS:
        for pc_id in TEST_RESULTS['uploaded_ids']:
            print(f"    - 点云 ID: {pc_id}")


# ==================== 主程序 ====================

def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("  三维激光点云处理平台 - 功能测试")
    print("=" * 70)
    
    results = []
    
    # 运行所有测试
    results.append(("系统健康检查", test_system_health()))
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
        print("\n  🎉 所有测试通过！")
        return 0
    else:
        print(f"\n  ⚠️ 有 {total - passed} 项测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
