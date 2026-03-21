from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Set, Optional
import json
import asyncio

from app.core.security import get_current_user_id_ws
from app.core.database import AsyncSessionLocal
from app.models.scene import Scene, SceneMember
from app.models.user import User

router = APIRouter(prefix="/ws")


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 场景ID -> {用户ID: WebSocket}
        self.scene_connections: Dict[int, Dict[int, WebSocket]] = {}
        # 用户ID -> {场景ID: 用户信息}
        self.user_info: Dict[int, Dict[int, dict]] = {}
    
    async def connect(self, websocket: WebSocket, scene_id: int, user_id: int, user_info: dict):
        """建立连接"""
        await websocket.accept()
        
        if scene_id not in self.scene_connections:
            self.scene_connections[scene_id] = {}
        
        self.scene_connections[scene_id][user_id] = websocket
        
        if user_id not in self.user_info:
            self.user_info[user_id] = {}
        
        self.user_info[user_id][scene_id] = {
            "id": user_id,
            "username": user_info.get("username"),
            "cursor_position": None,
            "view_matrix": None
        }
    
    def disconnect(self, scene_id: int, user_id: int):
        """断开连接"""
        if scene_id in self.scene_connections:
            self.scene_connections[scene_id].pop(user_id, None)
            if not self.scene_connections[scene_id]:
                del self.scene_connections[scene_id]
        
        if user_id in self.user_info:
            self.user_info[user_id].pop(scene_id, None)
            if not self.user_info[user_id]:
                del self.user_info[user_id]
    
    async def broadcast_to_scene(self, scene_id: int, message: dict, exclude_user_id: Optional[int] = None):
        """广播消息到场景（除指定用户外）"""
        if scene_id not in self.scene_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = []
        
        for user_id, websocket in self.scene_connections[scene_id].items():
            if exclude_user_id and user_id == exclude_user_id:
                continue
            
            try:
                await websocket.send_text(message_str)
            except Exception:
                disconnected.append((scene_id, user_id))
        
        # 清理断开的连接
        for sid, uid in disconnected:
            self.disconnect(sid, uid)
    
    async def send_to_user(self, scene_id: int, user_id: int, message: dict):
        """发送消息给指定用户"""
        if scene_id not in self.scene_connections:
            return
        
        websocket = self.scene_connections[scene_id].get(user_id)
        if websocket:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                self.disconnect(scene_id, user_id)
    
    def get_scene_users(self, scene_id: int) -> list:
        """获取场景中的所有用户信息"""
        if scene_id not in self.scene_connections:
            return []
        
        users = []
        for user_id in self.scene_connections[scene_id].keys():
            user_info = self.user_info.get(user_id, {}).get(scene_id)
            if user_info:
                users.append(user_info)
        
        return users
    
    def is_user_in_scene(self, scene_id: int, user_id: int) -> bool:
        """检查用户是否在场景中"""
        return scene_id in self.scene_connections and user_id in self.scene_connections[scene_id]


# 全局连接管理器
manager = ConnectionManager()


@router.websocket("/{scene_id}")
async def websocket_endpoint(websocket: WebSocket, scene_id: int):
    """WebSocket端点"""
    # 等待认证消息
    await websocket.accept()
    
    try:
        # 接收认证消息
        auth_message = await websocket.receive_text()
        auth_data = json.loads(auth_message)
        
        token = auth_data.get("token", "").replace("Bearer ", "")
        user_id = await get_current_user_id_ws(token)
        
        if user_id is None:
            await websocket.send_text(json.dumps({
                "type": "error",
                "code": "UNAUTHORIZED",
                "message": "Invalid or expired token"
            }))
            await websocket.close(code=4001)
            return
        
        # 验证用户是否有权限访问该场景
        async with AsyncSessionLocal() as db:
            # 获取场景
            result = await db.execute(
                select(Scene).where(Scene.id == scene_id)
            )
            scene = result.scalar_one_or_none()
            
            if not scene:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "SCENE_NOT_FOUND",
                    "message": "Scene not found"
                }))
                await websocket.close(code=4004)
                return
            
            # 检查权限
            result = await db.execute(
                select(SceneMember).where(
                    and_(SceneMember.scene_id == scene_id, SceneMember.user_id == user_id)
                )
            )
            is_member = result.scalar_one_or_none() is not None
            
            if scene.visibility == "private" and not is_member and scene.owner_id != user_id:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "ACCESS_DENIED",
                    "message": "Access denied"
                }))
                await websocket.close(code=4003)
                return
            
            # 获取用户信息
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one()
        
        # 建立连接
        user_info = {
            "id": user_id,
            "username": user.username,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url
        }
        
        await manager.connect(websocket, scene_id, user_id, user_info)
        
        # 通知其他用户有新用户加入
        await manager.broadcast_to_scene(scene_id, {
            "type": "user:joined",
            "data": {
                "user_id": user_id,
                "username": user.username,
                "joined_at": asyncio.get_event_loop().time()
            }
        }, exclude_user_id=user_id)
        
        # 发送当前场景中的用户列表给新用户
        active_users = manager.get_scene_users(scene_id)
        await websocket.send_text(json.dumps({
            "type": "scene:users",
            "data": {
                "active_users": active_users
            }
        }))
        
        # 处理消息
        try:
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                event_type = data.get("type")
                event_data = data.get("data", {})
                
                if event_type == "user:view_update":
                    # 更新用户视角
                    view_matrix = event_data.get("view_matrix")
                    cursor_position = event_data.get("cursor_position")
                    
                    # 更新用户信息
                    if user_id in manager.user_info and scene_id in manager.user_info[user_id]:
                        manager.user_info[user_id][scene_id]["view_matrix"] = view_matrix
                        manager.user_info[user_id][scene_id]["cursor_position"] = cursor_position
                    
                    # 广播给其他用户
                    await manager.broadcast_to_scene(scene_id, {
                        "type": "user:view_updated",
                        "data": {
                            "user_id": user_id,
                            "username": user.username,
                            "view_matrix": view_matrix,
                            "cursor_position": cursor_position
                        }
                    }, exclude_user_id=user_id)
                
                elif event_type == "pointcloud:transform":
                    # 更新点云变换
                    point_cloud_id = event_data.get("point_cloud_id")
                    transform = event_data.get("transform")
                    
                    # 广播给所有用户
                    await manager.broadcast_to_scene(scene_id, {
                        "type": "pointcloud:transform_updated",
                        "data": {
                            "point_cloud_id": point_cloud_id,
                            "transform": transform,
                            "updated_by": {
                                "id": user_id,
                                "username": user.username
                            }
                        }
                    })
                
                elif event_type == "pointcloud:visibility":
                    # 更新点云可见性
                    point_cloud_id = event_data.get("point_cloud_id")
                    visible = event_data.get("visible")
                    
                    await manager.broadcast_to_scene(scene_id, {
                        "type": "pointcloud:visibility_updated",
                        "data": {
                            "point_cloud_id": point_cloud_id,
                            "visible": visible,
                            "updated_by": {
                                "id": user_id,
                                "username": user.username
                            }
                        }
                    })
                
                elif event_type == "ping":
                    # 心跳响应
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": asyncio.get_event_loop().time()
                    }))
                
                else:
                    # 未知事件类型
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "UNKNOWN_EVENT",
                        "message": f"Unknown event type: {event_type}"
                    }))
        
        except WebSocketDisconnect:
            pass
        finally:
            # 断开连接
            manager.disconnect(scene_id, user_id)
            
            # 通知其他用户
            await manager.broadcast_to_scene(scene_id, {
                "type": "user:left",
                "data": {
                    "user_id": user_id,
                    "username": user.username
                }
            })
    
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "type": "error",
            "code": "INVALID_MESSAGE",
            "message": "Invalid JSON format"
        }))
        await websocket.close(code=4002)
    
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e)
        }))
        await websocket.close(code=4000)


# 用于其他模块调用的函数
async def notify_pointcloud_uploaded(scene_id: int, point_cloud_data: dict):
    """通知场景用户有新点云上传"""
    await manager.broadcast_to_scene(scene_id, {
        "type": "pointcloud:uploaded",
        "data": point_cloud_data
    })


async def notify_task_created(scene_id: int, task_data: dict):
    """通知场景用户有新任务创建"""
    await manager.broadcast_to_scene(scene_id, {
        "type": "task:created",
        "data": task_data
    })


async def notify_task_progress(scene_id: int, task_id: int, progress: float, status: str):
    """通知任务进度更新"""
    await manager.broadcast_to_scene(scene_id, {
        "type": "task:progress",
        "data": {
            "task_id": task_id,
            "progress": progress,
            "status": status
        }
    })


async def notify_task_completed(scene_id: int, task_id: int, result_point_cloud_id: int):
    """通知任务完成"""
    await manager.broadcast_to_scene(scene_id, {
        "type": "task:completed",
        "data": {
            "task_id": task_id,
            "result_point_cloud_id": result_point_cloud_id
        }
    })


async def notify_pointcloud_processing(scene_id: int, point_cloud_id: int, task_id: int, status: str, progress: float):
    """通知点云处理状态更新"""
    await manager.broadcast_to_scene(scene_id, {
        "type": "pointcloud:processing",
        "data": {
            "point_cloud_id": point_cloud_id,
            "task_id": task_id,
            "status": status,
            "progress": progress
        }
    })
