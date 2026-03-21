import asyncio
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8317/api/v1")


class TestClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.token = None
        self.user = None

    def login(self) -> bool:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": self.username, "password": self.password},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
            self._fetch_profile()
            return True
        print(f"登录失败: {resp.text}")
        return False

    def _fetch_profile(self) -> None:
        resp = requests.get(
            f"{BASE_URL}/auth/me",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            self.user = resp.json()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def upload_pointcloud(self, file_path: str, name: str) -> int | None:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/pointclouds/upload",
                headers=self._headers(),
                files={"file": (os.path.basename(file_path), f)},
                data={"name": name},
            )
        if resp.status_code == 200:
            return resp.json().get("id")
        print(f"上传失败: {resp.text}")
        return None

    def list_pointclouds(self) -> list:
        resp = requests.get(
            f"{BASE_URL}/pointclouds",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def create_task(self, pointcloud_id: int, task_type: str, params: dict | None = None) -> int | None:
        resp = requests.post(
            f"{BASE_URL}/tasks",
            headers=self._headers(),
            json={
                "pointcloud_id": pointcloud_id,
                "task_type": task_type,
                "parameters": params or {},
                "output_format": "ply",
            },
        )
        if resp.status_code == 200:
            return resp.json().get("id")
        print(f"创建任务失败: {resp.text}")
        return None

    def get_task(self, task_id: int) -> dict | None:
        resp = requests.get(
            f"{BASE_URL}/tasks",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            tasks = resp.json()
            for task in tasks:
                if task.get("id") == task_id:
                    return task
        return None

    def create_scene(self, name: str, description: str = "") -> int | None:
        resp = requests.post(
            f"{BASE_URL}/scenes",
            headers=self._headers(),
            json={"name": name, "description": description},
        )
        if resp.status_code == 200:
            return resp.json().get("id")
        print(f"创建场景失败: {resp.text}")
        return None

    def join_scene(self, scene_id: int) -> dict | None:
        resp = requests.post(
            f"{BASE_URL}/scenes/{scene_id}/join",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"加入场景失败: {resp.text}")
        return None

    def add_pointcloud_to_scene(self, scene_id: int, pointcloud_id: int) -> bool:
        resp = requests.post(
            f"{BASE_URL}/scenes/{scene_id}/pointclouds",
            headers=self._headers(),
            json={"pointcloud_id": pointcloud_id},
        )
        return resp.status_code == 200

    def get_scene(self, scene_id: int) -> dict | None:
        resp = requests.get(
            f"{BASE_URL}/scenes/{scene_id}",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        return None


def create_test_pointcloud(file_path: str, num_points: int = 10000) -> None:
    import random

    with open(file_path, "w") as f:
        for _ in range(num_points):
            x = random.uniform(-100, 100)
            y = random.uniform(-100, 100)
            z = random.uniform(-10, 50)
            f.write(f"{x:.6f} {y:.6f} {z:.6f}\n")


def create_large_pointcloud(file_path: str, size_mb: int = 50) -> None:
    import random

    target_bytes = size_mb * 1024 * 1024
    bytes_written = 0
    with open(file_path, "w") as f:
        while bytes_written < target_bytes:
            x = random.uniform(-1000, 1000)
            y = random.uniform(-1000, 1000)
            z = random.uniform(-100, 100)
            line = f"{x:.6f} {y:.6f} {z:.6f}\n"
            f.write(line)
            bytes_written += len(line)
    print(f"创建大文件: {file_path}, 大小: {bytes_written / 1024 / 1024:.2f} MB")


def test_multi_user_upload():
    print("\n=== 测试多用户同时上传点云 ===")

    users = [
        TestClient("admin", "admin123"),
        TestClient("engineer1", "engineer123"),
        TestClient("viewer1", "viewer123"),
    ]

    for user in users:
        if not user.login():
            print(f"用户 {user.username} 登录失败")
            return
        print(f"用户 {user.username} 登录成功")

    test_file = "/tmp/test_pointcloud.xyz"
    create_test_pointcloud(test_file)

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(user.upload_pointcloud, test_file, f"点云_{user.username}"): user.username
            for user in users
        }
        for future in futures:
            username = futures[future]
            try:
                pc_id = future.result(timeout=30)
                results[username] = pc_id
                print(f"用户 {username} 上传成功, 点云ID: {pc_id}")
            except Exception as e:
                print(f"用户 {username} 上传失败: {e}")

    print(f"上传结果: {results}")
    assert len(results) == 3, "应该有3个用户上传成功"


def test_concurrent_processing():
    print("\n=== 测试并发处理任务 ===")

    admin = TestClient("admin", "admin123")
    if not admin.login():
        print("管理员登录失败")
        return

    test_file = "/tmp/test_pointcloud_process.xyz"
    create_test_pointcloud(test_file, num_points=50000)

    pc_id = admin.upload_pointcloud(test_file, "处理测试点云")
    if not pc_id:
        print("上传失败")
        return

    print(f"上传成功, 点云ID: {pc_id}")

    task_types = ["voxel_grid_filter", "statistical_outlier_removal", "downsample"]
    task_ids = []

    for task_type in task_types:
        params = {}
        if task_type == "voxel_grid_filter":
            params = {"voxel_size": 0.5}
        elif task_type == "statistical_outlier_removal":
            params = {"nb_neighbors": 20, "std_ratio": 2.0}
        elif task_type == "downsample":
            params = {"ratio": 0.5}

        task_id = admin.create_task(pc_id, task_type, params)
        if task_id:
            task_ids.append(task_id)
            print(f"创建任务: {task_type}, 任务ID: {task_id}")

    print("等待任务完成...")
    time.sleep(10)

    for task_id in task_ids:
        task = admin.get_task(task_id)
        if task:
            print(f"任务 {task_id}: 状态={task.get('status')}, 进度={task.get('progress')}%")


def test_collaboration_scene():
    print("\n=== 测试协同场景功能 ===")

    users = [
        TestClient("admin", "admin123"),
        TestClient("engineer1", "engineer123"),
        TestClient("viewer1", "viewer123"),
    ]

    for user in users:
        user.login()

    scene_id = users[0].create_scene("协同测试场景", "用于测试多用户协同")
    if not scene_id:
        print("创建场景失败")
        return
    print(f"创建场景成功, ID: {scene_id}")

    test_file = "/tmp/test_collab.xyz"
    create_test_pointcloud(test_file)
    pc_id = users[0].upload_pointcloud(test_file, "协同点云")
    print(f"上传点云成功, ID: {pc_id}")

    if not users[0].add_pointcloud_to_scene(scene_id, pc_id):
        print("添加点云到场景失败")
        return
    print("添加点云到场景成功")

    for user in users:
        result = user.join_scene(scene_id)
        if result:
            print(f"用户 {user.username} 加入场景成功")
            scene_data = result.get("scene", {})
            sessions = scene_data.get("active_sessions", [])
            print(f"  当前在线用户: {len(sessions)}")


def test_large_file_upload():
    print("\n=== 测试大文件上传 ===")

    admin = TestClient("admin", "admin123")
    if not admin.login():
        print("登录失败")
        return

    large_file = "/tmp/large_pointcloud.xyz"
    create_large_pointcloud(large_file, size_mb=50)

    file_size = os.path.getsize(large_file) / 1024 / 1024
    print(f"准备上传 {file_size:.2f} MB 文件...")

    start_time = time.time()
    pc_id = admin.upload_pointcloud(large_file, "大文件测试")
    elapsed = time.time() - start_time

    if pc_id:
        print(f"上传成功! 点云ID: {pc_id}, 耗时: {elapsed:.2f}秒")
    else:
        print("上传失败")


def test_realtime_update():
    print("\n=== 测试实时更新 ===")

    admin = TestClient("admin", "admin123")
    engineer = TestClient("engineer1", "engineer123")

    admin.login()
    engineer.login()

    scene_id = admin.create_scene("实时更新测试场景")
    if not scene_id:
        print("创建场景失败")
        return

    admin.join_scene(scene_id)
    engineer.join_scene(scene_id)

    scene = admin.get_scene(scene_id)
    if scene:
        sessions = scene.get("active_sessions", [])
        print(f"场景在线用户数: {len(sessions)}")

        test_file = "/tmp/test_realtime.xyz"
        create_test_pointcloud(test_file)
        pc_id = admin.upload_pointcloud(test_file, "实时测试点云")

        if pc_id:
            admin.add_pointcloud_to_scene(scene_id, pc_id)

            scene_after = engineer.get_scene(scene_id)
            if scene_after:
                pointclouds = scene_after.get("pointclouds", [])
                print(f"工程师看到的场景点云数: {len(pointclouds)}")
                assert len(pointclouds) > 0, "工程师应该能看到新添加的点云"


def run_all_tests():
    print("=" * 60)
    print("开始运行测试用例")
    print("=" * 60)

    tests = [
        ("多用户同时上传", test_multi_user_upload),
        ("并发处理任务", test_concurrent_processing),
        ("协同场景功能", test_collaboration_scene),
        ("大文件上传", test_large_file_upload),
        ("实时更新", test_realtime_update),
    ]

    results = []
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, "PASS"))
        except Exception as e:
            print(f"测试 {name} 失败: {e}")
            results.append((name, "FAIL"))

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, status in results:
        print(f"  {name}: {status}")


if __name__ == "__main__":
    run_all_tests()
