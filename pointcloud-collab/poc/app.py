"""
点云协同处理系统 - PoC版本 (增强协同功能)
支持多用户在同一场景中实时协同可视化
"""
import os
import json
import uuid
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from pathlib import Path

import open3d as o3d
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

# ============ 配置 ============
SECRET_KEY = "poc-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ============ 数据库 ============
def init_db():
    """初始化SQLite数据库"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 场景表（协同空间）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            invite_code TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)
    
    # 场景成员表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scene_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scene_id, user_id),
            FOREIGN KEY (scene_id) REFERENCES scenes(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # 点云表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pointclouds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scene_id INTEGER,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            point_count INTEGER,
            status TEXT DEFAULT 'ready',
            is_visible BOOLEAN DEFAULT 1,
            transform_matrix TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (scene_id) REFERENCES scenes(id)
        )
    """)
    
    # 任务表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pointcloud_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            scene_id INTEGER,
            task_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            parameters TEXT,
            result_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pointcloud_id) REFERENCES pointclouds(id)
        )
    """)
    
    # 插入演示用户
    pwd_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash("demo123")
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, username, password_hash) 
        VALUES (1, 'demo', ?)
    """, (pwd_hash,))
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, username, password_hash) 
        VALUES (2, 'user2', ?)
    """, (pwd_hash,))
    
    # 创建默认场景
    cursor.execute("""
        INSERT OR IGNORE INTO scenes (id, name, owner_id, invite_code)
        VALUES (1, '协同测试场景', 1, 'COLLAB2024')
    """)
    
    # 添加成员
    cursor.execute("""
        INSERT OR IGNORE INTO scene_members (scene_id, user_id)
        VALUES (1, 1), (1, 2)
    """)
    
    conn.commit()
    conn.close()

init_db()

# ============ 认证 ============
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============ 协同状态管理 ============
@dataclass
class UserPresence:
    """用户在线状态"""
    user_id: int
    username: str
    websocket: WebSocket
    scene_id: Optional[int] = None
    camera_position: List[float] = field(default_factory=lambda: [5, 5, 5])
    camera_target: List[float] = field(default_factory=lambda: [0, 0, 0])
    selected_object: Optional[int] = None
    is_active: bool = True
    last_ping: datetime = field(default_factory=datetime.utcnow)

class CollaborationManager:
    """协同管理器 - 管理多用户场景同步"""
    
    def __init__(self):
        self.active_users: Dict[int, UserPresence] = {}  # user_id -> UserPresence
        self.scene_subscribers: Dict[int, set] = {}  # scene_id -> set(user_ids)
    
    async def connect(self, user_id: int, username: str, websocket: WebSocket):
        """用户连接"""
        await websocket.accept()
        
        # 如果用户已存在，先断开旧连接
        if user_id in self.active_users:
            old_ws = self.active_users[user_id].websocket
            try:
                await old_ws.close()
            except:
                pass
        
        presence = UserPresence(
            user_id=user_id,
            username=username,
            websocket=websocket
        )
        self.active_users[user_id] = presence
        
        print(f"[协同] 用户 {username}({user_id}) 已连接")
    
    def disconnect(self, user_id: int):
        """用户断开"""
        if user_id in self.active_users:
            presence = self.active_users[user_id]
            
            # 从场景中移除
            if presence.scene_id and presence.scene_id in self.scene_subscribers:
                self.scene_subscribers[presence.scene_id].discard(user_id)
                
                # 广播用户离开
                asyncio.create_task(self.broadcast_to_scene(
                    presence.scene_id,
                    {
                        "type": "user_left",
                        "data": {"user_id": user_id, "username": presence.username}
                    }
                ))
            
            del self.active_users[user_id]
            print(f"[协同] 用户 {presence.username}({user_id}) 已断开")
    
    async def join_scene(self, user_id: int, scene_id: int):
        """用户加入场景"""
        if user_id not in self.active_users:
            return
        
        presence = self.active_users[user_id]
        
        # 离开旧场景
        if presence.scene_id and presence.scene_id in self.scene_subscribers:
            self.scene_subscribers[presence.scene_id].discard(user_id)
        
        # 加入新场景
        presence.scene_id = scene_id
        if scene_id not in self.scene_subscribers:
            self.scene_subscribers[scene_id] = set()
        self.scene_subscribers[scene_id].add(user_id)
        
        # 获取场景中其他用户
        other_users = []
        for uid in self.scene_subscribers[scene_id]:
            if uid != user_id and uid in self.active_users:
                u = self.active_users[uid]
                other_users.append({
                    "user_id": uid,
                    "username": u.username,
                    "camera_position": u.camera_position,
                    "selected_object": u.selected_object
                })
        
        # 通知用户加入成功
        await presence.websocket.send_json({
            "type": "scene_joined",
            "data": {
                "scene_id": scene_id,
                "other_users": other_users
            }
        })
        
        # 广播给场景中其他用户
        await self.broadcast_to_scene(
            scene_id,
            {
                "type": "user_joined",
                "data": {
                    "user_id": user_id,
                    "username": presence.username
                }
            },
            exclude_user=user_id
        )
        
        print(f"[协同] 用户 {presence.username} 加入场景 {scene_id}")
    
    async def update_camera(self, user_id: int, position: List[float], target: List[float]):
        """更新相机位置"""
        if user_id not in self.active_users:
            return
        
        presence = self.active_users[user_id]
        presence.camera_position = position
        presence.camera_target = target
        
        # 广播给同场景其他用户
        if presence.scene_id:
            await self.broadcast_to_scene(
                presence.scene_id,
                {
                    "type": "camera_update",
                    "data": {
                        "user_id": user_id,
                        "username": presence.username,
                        "position": position,
                        "target": target
                    }
                },
                exclude_user=user_id
            )
    
    async def select_object(self, user_id: int, object_id: Optional[int], object_type: str = "pointcloud"):
        """用户选择对象"""
        if user_id not in self.active_users:
            return
        
        presence = self.active_users[user_id]
        presence.selected_object = object_id
        
        if presence.scene_id:
            await self.broadcast_to_scene(
                presence.scene_id,
                {
                    "type": "object_selected",
                    "data": {
                        "user_id": user_id,
                        "username": presence.username,
                        "object_id": object_id,
                        "object_type": object_type
                    }
                },
                exclude_user=user_id
            )
    
    async def broadcast_pointcloud_upload(self, scene_id: int, pointcloud_data: dict):
        """广播点云上传"""
        await self.broadcast_to_scene(
            scene_id,
            {
                "type": "pointcloud_uploaded",
                "data": pointcloud_data
            }
        )
    
    async def broadcast_processing_start(self, scene_id: int, task_data: dict):
        """广播处理开始"""
        await self.broadcast_to_scene(
            scene_id,
            {
                "type": "processing_started",
                "data": task_data
            }
        )
    
    async def broadcast_processing_complete(self, scene_id: int, task_data: dict):
        """广播处理完成"""
        await self.broadcast_to_scene(
            scene_id,
            {
                "type": "processing_completed",
                "data": task_data
            }
        )
    
    async def broadcast_to_scene(self, scene_id: int, message: dict, exclude_user: Optional[int] = None):
        """广播消息到场景"""
        if scene_id not in self.scene_subscribers:
            return
        
        disconnected = []
        for user_id in self.scene_subscribers[scene_id]:
            if user_id == exclude_user:
                continue
            
            if user_id in self.active_users:
                try:
                    await self.active_users[user_id].websocket.send_json(message)
                except:
                    disconnected.append(user_id)
            else:
                disconnected.append(user_id)
        
        # 清理断开的用户
        for uid in disconnected:
            self.scene_subscribers[scene_id].discard(uid)
    
    def get_scene_users(self, scene_id: int) -> List[dict]:
        """获取场景中的所有用户"""
        if scene_id not in self.scene_subscribers:
            return []
        
        users = []
        for uid in self.scene_subscribers[scene_id]:
            if uid in self.active_users:
                u = self.active_users[uid]
                users.append({
                    "user_id": uid,
                    "username": u.username,
                    "camera_position": u.camera_position,
                    "selected_object": u.selected_object
                })
        return users

collab_manager = CollaborationManager()

# ============ 点云处理 ============
class PointCloudProcessor:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.pcd = None
    
    def load(self):
        """加载点云"""
        self.pcd = o3d.io.read_point_cloud(self.file_path)
        return self.pcd
    
    def get_info(self):
        """获取点云信息"""
        if self.pcd is None:
            self.load()
        
        points = np.asarray(self.pcd.points)
        return {
            "point_count": len(points),
            "has_color": self.pcd.has_colors(),
            "bounds": {
                "min": points.min(axis=0).tolist() if len(points) > 0 else [0, 0, 0],
                "max": points.max(axis=0).tolist() if len(points) > 0 else [0, 0, 0]
            }
        }
    
    def voxel_downsample(self, voxel_size: float = 0.05):
        """体素下采样"""
        if self.pcd is None:
            self.load()
        return self.pcd.voxel_down_sample(voxel_size)
    
    def remove_outliers(self, nb_neighbors: int = 20, std_ratio: float = 2.0):
        """统计离群点移除"""
        if self.pcd is None:
            self.load()
        cl, ind = self.pcd.remove_statistical_outlier(nb_neighbors, std_ratio)
        return self.pcd.select_by_index(ind)
    
    def segment_plane(self, distance_threshold: float = 0.01, num_iterations: int = 1000):
        """RANSAC平面分割"""
        if self.pcd is None:
            self.load()
        
        plane_model, inliers = self.pcd.segment_plane(
            distance_threshold=distance_threshold,
            ransac_n=3,
            num_iterations=num_iterations
        )
        
        inlier_cloud = self.pcd.select_by_index(inliers)
        outlier_cloud = self.pcd.select_by_index(inliers, invert=True)
        
        return inlier_cloud, outlier_cloud, plane_model
    
    def save(self, pcd, output_path: str):
        """保存点云"""
        o3d.io.write_point_cloud(output_path, pcd)
        return output_path

# ============ FastAPI应用 ============
app = FastAPI(title="点云协同处理系统 - PoC (增强协同)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ API路由 ============

@app.post("/api/auth/login")
async def login(credentials: dict):
    """用户登录"""
    username = credentials.get("username")
    password = credentials.get("password")
    
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not pwd_context.verify(password, user[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(
        data={"sub": str(user[0])},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "code": 200,
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"id": user[0], "username": user[2]}
        }
    }

@app.get("/api/scenes")
async def list_scenes(user_id: int = Depends(get_current_user)):
    """获取用户的场景列表"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    
    # 获取用户加入的场景
    cursor.execute("""
        SELECT s.id, s.name, s.invite_code, u.username as owner
        FROM scenes s
        JOIN scene_members sm ON s.id = sm.scene_id
        JOIN users u ON s.owner_id = u.id
        WHERE sm.user_id = ?
    """, (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "code": 200,
        "data": {
            "items": [
                {
                    "id": row[0],
                    "name": row[1],
                    "invite_code": row[2],
                    "owner": row[3]
                }
                for row in rows
            ]
        }
    }

@app.post("/api/scenes/{scene_id}/join")
async def join_scene(scene_id: int, user_id: int = Depends(get_current_user)):
    """加入场景"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    
    # 检查场景是否存在
    cursor.execute("SELECT id FROM scenes WHERE id = ?", (scene_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # 添加成员
    cursor.execute("""
        INSERT OR IGNORE INTO scene_members (scene_id, user_id)
        VALUES (?, ?)
    """, (scene_id, user_id))
    conn.commit()
    conn.close()
    
    return {"code": 200, "message": "Joined scene successfully"}

@app.get("/api/scenes/{scene_id}/pointclouds")
async def get_scene_pointclouds(scene_id: int, user_id: int = Depends(get_current_user)):
    """获取场景中的点云"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.id, p.name, p.filename, p.point_count, p.status, p.user_id, p.is_visible,
               u.username as owner_name
        FROM pointclouds p
        JOIN users u ON p.user_id = u.id
        WHERE p.scene_id = ? AND p.is_visible = 1
        ORDER BY p.created_at DESC
    """, (scene_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "code": 200,
        "data": {
            "items": [
                {
                    "id": row[0],
                    "name": row[1],
                    "filename": row[2],
                    "point_count": row[3],
                    "status": row[4],
                    "user_id": row[5],
                    "is_visible": row[6],
                    "owner_name": row[7]
                }
                for row in rows
            ]
        }
    }

@app.get("/api/pointclouds")
async def list_pointclouds(user_id: int = Depends(get_current_user)):
    """获取点云列表"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, filename, point_count, status, created_at 
        FROM pointclouds ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "code": 200,
        "data": {
            "items": [
                {
                    "id": row[0],
                    "name": row[1],
                    "filename": row[2],
                    "point_count": row[3],
                    "status": row[4],
                    "created_at": row[5]
                }
                for row in rows
            ]
        }
    }

@app.post("/api/scenes/{scene_id}/pointclouds/upload")
async def upload_pointcloud_to_scene(
    scene_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    user_id: int = Depends(get_current_user)
):
    """上传点云到场景"""
    # 保存文件
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # 处理点云
    try:
        processor = PointCloudProcessor(str(file_path))
        info = processor.get_info()
        
        # 保存到数据库
        conn = sqlite3.connect("poc.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pointclouds (user_id, scene_id, name, filename, file_path, file_size, point_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, scene_id, name, file.filename, str(file_path), len(content), info["point_count"]))
        
        pc_id = cursor.lastrowid
        
        # 获取用户名
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        username = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # 广播给场景中的所有用户
        await collab_manager.broadcast_pointcloud_upload(
            scene_id,
            {
                "id": pc_id,
                "name": name,
                "filename": file.filename,
                "point_count": info["point_count"],
                "user_id": user_id,
                "username": username,
                "scene_id": scene_id
            }
        )
        
        return {
            "code": 200,
            "data": {
                "id": pc_id,
                "name": name,
                "point_count": info["point_count"]
            }
        }
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=400, detail=f"处理失败: {str(e)}")

@app.get("/api/pointclouds/{pc_id}")
async def get_pointcloud(pc_id: int, user_id: int = Depends(get_current_user)):
    """获取点云详情"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pointclouds WHERE id = ?", (pc_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Point cloud not found")
    
    processor = PointCloudProcessor(row[4])
    info = processor.get_info()
    
    return {
        "code": 200,
        "data": {
            "id": row[0],
            "name": row[2],
            "filename": row[3],
            "point_count": info["point_count"],
            "bounds": info["bounds"],
            "has_color": info["has_color"],
            "scene_id": row[7]
        }
    }

@app.get("/api/pointclouds/{pc_id}/download")
async def download_pointcloud(pc_id: int, user_id: int = Depends(get_current_user)):
    """下载点云文件"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_path, filename FROM pointclouds WHERE id = ?", (pc_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Point cloud not found")
    
    return FileResponse(row[0], filename=row[1])

@app.post("/api/pointclouds/{pc_id}/process")
async def process_pointcloud(
    pc_id: int,
    params: dict,
    user_id: int = Depends(get_current_user)
):
    """处理点云"""
    task_type = params.get("task_type")
    scene_id = params.get("scene_id")
    
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_path, name FROM pointclouds WHERE id = ?", (pc_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Point cloud not found")
    
    file_path, name = row
    
    # 获取用户名
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    username = cursor.fetchone()[0]
    
    # 创建任务记录
    cursor.execute("""
        INSERT INTO tasks (pointcloud_id, user_id, scene_id, task_type, parameters, status)
        VALUES (?, ?, ?, ?, ?, 'running')
    """, (pc_id, user_id, scene_id, task_type, json.dumps(params)))
    task_id = cursor.lastrowid
    conn.commit()
    
    # 广播处理开始
    if scene_id:
        await collab_manager.broadcast_processing_start(
            scene_id,
            {
                "task_id": task_id,
                "pointcloud_id": pc_id,
                "pointcloud_name": name,
                "task_type": task_type,
                "user_id": user_id,
                "username": username
            }
        )
    
    try:
        # 执行处理
        processor = PointCloudProcessor(file_path)
        processor.load()
        
        if task_type == "voxel":
            voxel_size = params.get("voxel_size", 0.05)
            result = processor.voxel_downsample(voxel_size)
        elif task_type == "outlier":
            nb_neighbors = params.get("nb_neighbors", 20)
            std_ratio = params.get("std_ratio", 2.0)
            result = processor.remove_outliers(nb_neighbors, std_ratio)
        elif task_type == "segment":
            distance_threshold = params.get("distance_threshold", 0.01)
            inlier_cloud, outlier_cloud, plane_model = processor.segment_plane(distance_threshold)
            result = inlier_cloud
        else:
            raise ValueError(f"Unknown task type: {task_type}")
        
        # 保存结果
        result_id = str(uuid.uuid4())
        result_path = UPLOAD_DIR / f"{result_id}_result.ply"
        processor.save(result, str(result_path))
        
        # 添加结果到场景
        if scene_id:
            cursor.execute("""
                INSERT INTO pointclouds (user_id, scene_id, name, filename, file_path, file_size, point_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ready')
            """, (user_id, scene_id, f"{name}_{task_type}", f"result_{task_type}.ply", 
                  str(result_path), 0, len(result.points)))
            result_pc_id = cursor.lastrowid
        
        # 更新任务状态
        cursor.execute("""
            UPDATE tasks SET status = 'completed', result_path = ? WHERE id = ?
        """, (str(result_path), task_id))
        conn.commit()
        
        # 广播处理完成
        if scene_id:
            await collab_manager.broadcast_processing_complete(
                scene_id,
                {
                    "task_id": task_id,
                    "pointcloud_id": pc_id,
                    "pointcloud_name": name,
                    "result_pointcloud_id": result_pc_id if scene_id else None,
                    "task_type": task_type,
                    "user_id": user_id,
                    "username": username,
                    "result_point_count": len(result.points)
                }
            )
        
        conn.close()
        
        return {
            "code": 200,
            "data": {
                "task_id": task_id,
                "status": "completed",
                "result_point_count": len(result.points)
            }
        }
        
    except Exception as e:
        cursor.execute("UPDATE tasks SET status = 'failed' WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks")
async def list_tasks(user_id: int = Depends(get_current_user)):
    """获取任务列表"""
    conn = sqlite3.connect("poc.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.task_type, t.status, t.created_at, p.name 
        FROM tasks t
        JOIN pointclouds p ON t.pointcloud_id = p.id
        ORDER BY t.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "code": 200,
        "data": {
            "items": [
                {
                    "id": row[0],
                    "task_type": row[1],
                    "status": row[2],
                    "created_at": row[3],
                    "pointcloud_name": row[4]
                }
                for row in rows
            ]
        }
    }

# ============ WebSocket协同 ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket协同连接"""
    # 等待认证消息
    try:
        auth_msg = await websocket.receive_json()
        if auth_msg.get("type") != "auth":
            await websocket.close(code=4001, reason="Auth required")
            return
        
        token = auth_msg.get("token")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = int(payload.get("sub"))
        except:
            await websocket.close(code=4002, reason="Invalid token")
            return
        
        # 获取用户名
        conn = sqlite3.connect("poc.db")
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        conn.close()
        
        if not user_row:
            await websocket.close(code=4003, reason="User not found")
            return
        
        username = user_row[0]
        
        # 连接协同管理器
        await collab_manager.connect(user_id, username, websocket)
        
        try:
            while True:
                msg = await websocket.receive_json()
                msg_type = msg.get("type")
                
                if msg_type == "join_scene":
                    scene_id = msg.get("scene_id")
                    await collab_manager.join_scene(user_id, scene_id)
                
                elif msg_type == "camera_update":
                    position = msg.get("position")
                    target = msg.get("target")
                    await collab_manager.update_camera(user_id, position, target)
                
                elif msg_type == "select_object":
                    object_id = msg.get("object_id")
                    object_type = msg.get("object_type", "pointcloud")
                    await collab_manager.select_object(user_id, object_id, object_type)
                
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                
        except WebSocketDisconnect:
            collab_manager.disconnect(user_id)
        
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass

# ============ 前端页面 ============

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面 - 增强协同功能"""
    return open("/Users/lh/JSP/Kimi k 2.5/rz_sanweijiguangdianyun/pointcloud-collab/poc/templates/index.html").read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
