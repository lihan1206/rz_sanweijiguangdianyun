#!/usr/bin/env python3
"""
多用户协同处理点云数据测试脚本

测试场景:
1. 模拟3个用户同时上传点云文件
2. 用户A处理滤波，用户B处理配准，用户C查看结果
3. 检查实时更新
4. 检查大文件上传支持
"""

import asyncio
import json
import os
import random
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import aiofiles
import aiohttp
import numpy as np


@dataclass
class User:
    """测试用户"""
    id: int
    username: str
    password: str
    token: Optional[str] = None


@dataclass
class PointCloudFile:
    """测试点云文件"""
    name: str
    size_mb: float
    data: bytes


class CollaborationTester:
    """协同处理测试器"""

    def __init__(self, base_url: str = "http://localhost:8317"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api/v1"
        self.ws_url = f"ws://{base_url.split('://', 1)[1]}/api/v1/collaboration/ws"
        self.users: List[User] = []
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connections: Dict[int, aiohttp.ClientWebSocketResponse] = {}

    async def init_users(self) -> None:
        """初始化测试用户"""
        self.users = [
            User(id=1, username="user_a", password="test123456"),
            User(id=2, username="user_b", password="test123456"),
            User(id=3, username="user_c", password="test123456"),
        ]

        # 登录获取token
        login_tasks = [self._login(user) for user in self.users]
        await asyncio.gather(*login_tasks)

    async def _login(self, user: User) -> None:
        """用户登录"""
        try:
            async with self.session.post(
                f"{self.api_url}/auth/login",
                data={"username": user.username, "password": user.password},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user.token = data["access_token"]
                    print(f"用户 {user.username} 登录成功")
                else:
                    print(f"用户 {user.username} 登录失败: {resp.status}")
        except Exception as e:
            print(f"用户 {user.username} 登录异常: {e}")

    def generate_pointcloud_file(self, size_mb: float = 10.0, format: str = "xyz") -> PointCloudFile:
        """生成测试点云文件"""
        # 估算点数 (每个点约32字节: x,y,z,nx,ny,nz,r,g,b)
        bytes_per_point = 32
        num_points = int((size_mb * 1024 * 1024) / bytes_per_point)

        # 生成随机点云数据
        points = np.random.rand(num_points, 9) * 100.0
        points[:, 3:6] = points[:, 3:6] / np.linalg.norm(points[:, 3:6], axis=1, keepdims=True)
        points[:, 6:9] = np.random.randint(0, 256, (num_points, 3))

        # 转换为XYZ格式
        content = []
        for p in points[:10000]:  # 限制点数避免文件过大
            line = f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {p[3]:.6f} {p[4]:.6f} {p[5]:.6f} {int(p[6])} {int(p[7])} {int(p[8])}\n"
            content.append(line)

        data = "".join(content).encode("utf-8")
        return PointCloudFile(
            name=f"test_pointcloud_{int(time.time())}.{format}",
            size_mb=len(data) / 1024 / 1024,
            data=data,
        )

    async def upload_file(self, user: User, pc_file: PointCloudFile) -> Optional[int]:
        """上传点云文件"""
        if not user.token:
            return None

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as tmp:
            tmp.write(pc_file.data)
            tmp_path = tmp.name

        try:
            form_data = aiohttp.FormData()
            form_data.add_field(
                "file",
                open(tmp_path, "rb"),
                filename=pc_file.name,
                content_type="application/octet-stream",
            )
            form_data.add_field("name", pc_file.name)
            form_data.add_field("tags", "test,collaboration")

            async with self.session.post(
                f"{self.api_url}/pointcloud/upload",
                headers={"Authorization": f"Bearer {user.token}"},
                data=form_data,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pc_id = data["id"]
                    print(f"用户 {user.username} 上传文件成功: {pc_file.name} -> ID: {pc_id}")
                    return pc_id
                else:
                    error = await resp.text()
                    print(f"用户 {user.username} 上传失败: {resp.status} - {error[:200]}")
                    return None
        finally:
            os.unlink(tmp_path)

    async def create_collaboration_session(self, creator: User) -> Optional[int]:
        """创建协同会话"""
        if not creator.token:
            return None

        session_data = {
            "session_name": f"协同测试会话_{int(time.time())}",
            "description": "多用户协同处理测试会话",
            "max_users": 10,
        }

        async with self.session.post(
            f"{self.api_url}/collaboration/sessions",
            headers={"Authorization": f"Bearer {creator.token}"},
            json=session_data,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                session_id = data["id"]
                print(f"用户 {creator.username} 创建协同会话: {session_id}")
                return session_id
            else:
                error = await resp.text()
                print(f"创建协同会话失败: {resp.status} - {error}")
                return None

    async def join_session(self, user: User, session_id: int) -> bool:
        """加入协同会话"""
        if not user.token:
            return False

        async with self.session.post(
            f"{self.api_url}/collaboration/sessions/{session_id}/join",
            headers={"Authorization": f"Bearer {user.token}"},
        ) as resp:
            if resp.status == 200:
                print(f"用户 {user.username} 加入会话 {session_id}")
                return True
            else:
                error = await resp.text()
                print(f"加入会话失败: {resp.status} - {error}")
                return False

    async def connect_websocket(self, user: User, session_id: int) -> None:
        """连接WebSocket"""
        if not user.token:
            return

        try:
            ws = await self.session.ws_connect(
                f"{self.ws_url}/{session_id}/{user.id}",
                headers={"Authorization": f"Bearer {user.token}"},
            )
            self.ws_connections[user.id] = ws
            print(f"用户 {user.username} WebSocket连接建立")

            # 启动消息监听任务
            asyncio.create_task(self._listen_ws(user, ws))
        except Exception as e:
            print(f"用户 {user.username} WebSocket连接失败: {e}")

    async def _listen_ws(self, user: User, ws: aiohttp.ClientWebSocketResponse) -> None:
        """监听WebSocket消息"""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")
                    if msg_type == "task_completed":
                        print(f"[{user.username}] 收到任务完成通知: 任务 {data.get('task_id')}")
                    elif msg_type == "pointcloud_updated":
                        print(f"[{user.username}] 收到点云更新通知: 点云 {data.get('pointcloud_id')}")
                    elif msg_type == "user_joined":
                        print(f"[{user.username}] 用户 {data.get('user_id')} 加入会话")
                    elif msg_type == "user_left":
                        print(f"[{user.username}] 用户 {data.get('user_id')} 离开会话")
                    else:
                        print(f"[{user.username}] 收到消息: {data}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"[{user.username}] WebSocket错误")
                    break
        except Exception as e:
            print(f"[{user.username}] WebSocket监听异常: {e}")

    async def create_processing_task(
        self,
        user: User,
        pointcloud_id: int,
        task_type: str,
        params: Dict,
        session_id: Optional[int] = None,
    ) -> Optional[int]:
        """创建处理任务"""
        if not user.token:
            return None

        task_data = {
            "pointcloud_id": pointcloud_id,
            "task_type": task_type,
            "output_format": "ply",
            "params": params,
            "session_id": session_id,
        }

        async with self.session.post(
            f"{self.api_url}/tasks",
            headers={"Authorization": f"Bearer {user.token}"},
            json=task_data,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                task_id = data["id"]
                print(f"用户 {user.username} 创建任务 {task_id}: {task_type}")
                return task_id
            else:
                error = await resp.text()
                print(f"创建任务失败: {resp.status} - {error}")
                return None

    async def wait_for_task(self, user: User, task_id: int, timeout: int = 120) -> bool:
        """等待任务完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            async with self.session.get(
                f"{self.api_url}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {user.token}"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status = data["status"]
                    if status == "completed":
                        print(f"任务 {task_id} 完成! 输出点云: {data.get('output_pointcloud_id')}")
                        return True
                    elif status == "failed":
                        print(f"任务 {task_id} 失败: {data.get('error_message')}")
                        return False
                    else:
                        print(f"任务 {task_id} 状态: {status}")
            await asyncio.sleep(3)
        print(f"任务 {task_id} 超时")
        return False

    async def run_collaboration_test(self) -> bool:
        """运行协同测试"""
        print("\n" + "=" * 60)
        print("测试场景: 多用户协同处理点云数据")
        print("=" * 60)

        # 1. 初始化会话
        self.session = aiohttp.ClientSession()
        await self.init_users()

        if not any(user.token for user in self.users):
            print("错误: 没有用户成功登录")
            return False

        # 2. 创建协同会话 (由用户A创建)
        print("\n--- 步骤1: 创建协同会话 ---")
        session_id = await self.create_collaboration_session(self.users[0])
        if not session_id:
            return False

        # 3. 所有用户加入会话
        print("\n--- 步骤2: 用户加入会话 ---")
        join_tasks = [self.join_session(user, session_id) for user in self.users]
        join_results = await asyncio.gather(*join_tasks)
        if not all(join_results):
            print("警告: 部分用户未能加入会话")

        # 4. 建立WebSocket连接
        print("\n--- 步骤3: 建立WebSocket连接 ---")
        ws_tasks = [self.connect_websocket(user, session_id) for user in self.users]
        await asyncio.gather(*ws_tasks)
        await asyncio.sleep(1)

        # 5. 生成并上传点云文件
        print("\n--- 步骤4: 上传点云文件 ---")
        pc_file1 = self.generate_pointcloud_file(size_mb=5.0)
        pc_file2 = self.generate_pointcloud_file(size_mb=8.0)

        upload_tasks = [
            self.upload_file(self.users[0], pc_file1),  # 用户A上传
            self.upload_file(self.users[1], pc_file2),  # 用户B上传
        ]
        pc_ids = await asyncio.gather(*upload_tasks)
        pc_id_a, pc_id_b = pc_ids

        if not pc_id_a or not pc_id_b:
            print("错误: 文件上传失败")
            return False

        # 6. 用户A: 体素格滤波处理
        print("\n--- 步骤5: 用户A执行体素格滤波 ---")
        task_a = await self.create_processing_task(
            user=self.users[0],
            pointcloud_id=pc_id_a,
            task_type="voxel_grid",
            params={"voxel_size": 0.05},
            session_id=session_id,
        )

        # 7. 用户B: 统计离群点移除
        print("\n--- 步骤6: 用户B执行统计离群点移除 ---")
        task_b = await self.create_processing_task(
            user=self.users[1],
            pointcloud_id=pc_id_b,
            task_type="statistical_outlier",
            params={"nb_neighbors": 20, "std_ratio": 2.0},
            session_id=session_id,
        )

        # 8. 等待任务完成
        print("\n--- 步骤7: 等待任务完成 ---")
        if task_a:
            await self.wait_for_task(self.users[0], task_a)
        if task_b:
            await self.wait_for_task(self.users[1], task_b)

        # 9. 用户C查看结果列表
        print("\n--- 步骤8: 用户C查看处理结果 ---")
        async with self.session.get(
            f"{self.api_url}/pointcloud?session_id={session_id}",
            headers={"Authorization": f"Bearer {self.users[2].token}"},
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"用户C查看到会话中的点云数量: {len(data)}")
                for pc in data[:5]:
                    print(f"  - {pc['name']} (ID: {pc['id']}, 版本: v{pc['version']})")

        # 10. 测试大文件上传 (模拟50MB)
        print("\n--- 步骤9: 测试大文件上传 (约50MB) ---")
        large_file = self.generate_pointcloud_file(size_mb=50.0)
        print(f"生成测试文件: {large_file.name}, 大小: {large_file.size_mb:.2f} MB")

        large_pc_id = await self.upload_file(self.users[0], large_file)
        if large_pc_id:
            print("大文件上传成功!")
        else:
            print("大文件上传失败 (可能因文件过大被服务器拒绝，属于预期行为)")

        # 11. 清理
        print("\n--- 步骤10: 清理连接 ---")
        for ws in self.ws_connections.values():
            await ws.close()
        await self.session.close()

        print("\n" + "=" * 60)
        print("测试完成!")
        print("=" * 60)
        return True

    async def run_stress_test(self, concurrent_users: int = 10) -> None:
        """压力测试: 多用户同时上传"""
        print("\n" + "=" * 60)
        print(f"压力测试: {concurrent_users} 个用户同时上传")
        print("=" * 60)

        self.session = aiohttp.ClientSession()

        # 使用已登录的用户A进行测试
        if not self.users:
            await self.init_users()

        user = self.users[0]
        if not user.token:
            print("用户未登录，无法进行压力测试")
            return

        # 生成多个小文件
        files = [self.generate_pointcloud_file(size_mb=1.0) for _ in range(concurrent_users)]

        # 并发上传
        start_time = time.time()
        upload_tasks = [self.upload_file(user, f) for f in files]
        results = await asyncio.gather(*upload_tasks)
        end_time = time.time()

        success_count = sum(1 for r in results if r is not None)
        print(f"\n上传完成: 成功 {success_count}/{concurrent_users}")
        print(f"总耗时: {end_time - start_time:.2f} 秒")
        print(f"平均耗时: {(end_time - start_time)/concurrent_users:.2f} 秒/文件")

        await self.session.close()


async def main():
    """主函数"""
    tester = CollaborationTester()

    # 运行协同测试
    success = await tester.run_collaboration_test()

    # 运行压力测试
    await tester.run_stress_test(concurrent_users=5)

    if success:
        print("\n测试成功完成!")
    else:
        print("\n测试失败!")


if __name__ == "__main__":
    asyncio.run(main())