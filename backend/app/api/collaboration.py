import asyncio
import json
import logging
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.core.exceptions import (
    ErrorCode,
    SceneException,
    raise_scene_error,
)
from app.models.collaboration import CollaborationScene, CollaborationSession, ScenePointCloud
from app.models.pointcloud import PointCloud
from app.models.user import User, UserRole
from app.schemas.collaboration import (
    CameraUpdateRequest,
    SceneCreateRequest,
    SceneCreateResponse,
    SceneDetail,
    SceneJoinResponse,
    SceneListItem,
    ScenePointCloudAddRequest,
    ScenePointCloudItem,
    ScenePointCloudUpdateRequest,
    SceneUpdateRequest,
    SessionInfo,
)
from app.services.audit import write_audit_log

router = APIRouter(prefix="/scenes", tags=["协同场景"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = {}
        self.session_map: dict[str, tuple[int, int]] = {}

    async def connect(self, websocket: WebSocket, scene_id: int, user_id: int, session_token: str) -> None:
        try:
            await websocket.accept()
            if scene_id not in self.active_connections:
                self.active_connections[scene_id] = []
            self.active_connections[scene_id].append(websocket)
            self.session_map[session_token] = (scene_id, user_id)
        except Exception as e:
            logger.exception("WebSocket连接失败: scene_id=%s, user_id=%s", scene_id, user_id)
            raise

    def disconnect(self, websocket: WebSocket, scene_id: int, session_token: str) -> None:
        try:
            if scene_id in self.active_connections:
                if websocket in self.active_connections[scene_id]:
                    self.active_connections[scene_id].remove(websocket)
                if not self.active_connections[scene_id]:
                    del self.active_connections[scene_id]
            if session_token in self.session_map:
                del self.session_map[session_token]
        except Exception:
            logger.exception("WebSocket断开连接处理失败")

    async def broadcast_to_scene(self, scene_id: int, message: dict[str, Any], exclude: WebSocket | None = None) -> None:
        if scene_id not in self.active_connections:
            return
        connections = self.active_connections[scene_id].copy()
        for connection in connections:
            if connection != exclude:
                try:
                    await connection.send_json(message)
                except Exception:
                    logger.exception("广播消息失败")

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            logger.exception("发送个人消息失败")

    def get_active_users(self, scene_id: int) -> int:
        return len(self.active_connections.get(scene_id, []))


manager = ConnectionManager()


def get_scene_or_404(db: Session, scene_id: int) -> CollaborationScene:
    scene = db.query(CollaborationScene).filter(CollaborationScene.id == scene_id).first()
    if not scene:
        raise_scene_error(
            ErrorCode.SCENE_NOT_FOUND,
            f"场景不存在: {scene_id}",
        )
    return scene


def get_session_or_404(db: Session, session_token: str, user_id: int) -> CollaborationSession:
    session = db.query(CollaborationSession).filter(
        CollaborationSession.session_token == session_token,
        CollaborationSession.user_id == user_id,
    ).first()
    if not session:
        raise_scene_error(
            ErrorCode.SCENE_SESSION_NOT_FOUND,
            "会话不存在",
        )
    return session


@router.get("", response_model=list[SceneListItem])
def list_scenes(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SceneListItem]:
    try:
        query = db.query(CollaborationScene)
        if not include_inactive:
            query = query.filter(CollaborationScene.is_active.is_(True))
        scenes = query.order_by(CollaborationScene.created_at.desc()).all()

        result = []
        for scene in scenes:
            try:
                pointcloud_count = db.query(ScenePointCloud).filter(ScenePointCloud.scene_id == scene.id).count()
                active_users = db.query(CollaborationSession).filter(
                    CollaborationSession.scene_id == scene.id,
                    CollaborationSession.is_active.is_(True),
                ).count()

                result.append(SceneListItem(
                    id=scene.id,
                    name=scene.name,
                    description=scene.description,
                    is_active=scene.is_active,
                    max_users=scene.max_users,
                    created_by=scene.created_by,
                    created_by_name=scene.creator.username if scene.creator else "未知",
                    created_at=scene.created_at,
                    pointcloud_count=pointcloud_count,
                    active_users=active_users,
                ))
            except Exception:
                logger.exception("获取场景信息失败: scene_id=%s", scene.id)
                continue
        return result
    except SQLAlchemyError:
        logger.exception("查询场景列表失败")
        raise HTTPException(status_code=500, detail="查询场景列表失败")


@router.post("", response_model=SceneCreateResponse)
def create_scene(
    payload: SceneCreateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> SceneCreateResponse:
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="场景名称不能为空")

    if payload.max_users is not None and payload.max_users < 1:
        raise HTTPException(status_code=400, detail="最大用户数必须大于0")

    try:
        scene = CollaborationScene(
            name=payload.name.strip(),
            description=payload.description,
            max_users=payload.max_users or 10,
            settings=payload.settings,
            created_by=current_user.id,
        )
        db.add(scene)
        db.flush()

        write_audit_log(
            db,
            action="创建协同场景",
            target_type="collaboration_scene",
            target_id=str(scene.id),
            user_id=current_user.id,
            detail={"name": payload.name},
        )
        db.commit()

        return SceneCreateResponse(id=scene.id, message="场景创建成功")
    except SQLAlchemyError:
        logger.exception("创建场景失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="创建场景失败")


@router.get("/{scene_id}", response_model=SceneDetail)
def get_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SceneDetail:
    scene = get_scene_or_404(db, scene_id)

    try:
        scene_pcs = db.query(ScenePointCloud).filter(ScenePointCloud.scene_id == scene_id).order_by(ScenePointCloud.order).all()
        pointclouds = []
        for spc in scene_pcs:
            try:
                pointclouds.append(
                    ScenePointCloudItem(
                        id=spc.id,
                        scene_id=spc.scene_id,
                        pointcloud_id=spc.pointcloud_id,
                        pointcloud_name=spc.pointcloud.name if spc.pointcloud else "未知",
                        transform_matrix=spc.transform_matrix,
                        visible=spc.visible,
                        color=spc.color,
                        opacity=spc.opacity,
                        order=spc.order,
                        added_by=spc.added_by,
                        added_by_name=spc.adder.username if spc.adder else "未知",
                        added_at=spc.added_at,
                    )
                )
            except Exception:
                logger.exception("获取场景点云信息失败: spc_id=%s", spc.id)
                continue
    except SQLAlchemyError:
        logger.exception("查询场景点云失败")
        pointclouds = []

    try:
        active_sessions = db.query(CollaborationSession).filter(
            CollaborationSession.scene_id == scene_id,
            CollaborationSession.is_active.is_(True),
        ).all()
        sessions = [
            SessionInfo(
                id=sess.id,
                user_id=sess.user_id,
                username=sess.user.username if sess.user else "未知",
                camera_position=sess.camera_position,
                camera_target=sess.camera_target,
                is_active=sess.is_active,
                joined_at=sess.joined_at,
            )
            for sess in active_sessions
        ]
    except SQLAlchemyError:
        logger.exception("查询活跃会话失败")
        sessions = []

    return SceneDetail(
        id=scene.id,
        name=scene.name,
        description=scene.description,
        is_active=scene.is_active,
        max_users=scene.max_users,
        settings=scene.settings,
        created_by=scene.created_by,
        created_by_name=scene.creator.username if scene.creator else "未知",
        created_at=scene.created_at,
        updated_at=scene.updated_at,
        pointclouds=pointclouds,
        active_sessions=sessions,
    )


@router.put("/{scene_id}", response_model=SceneCreateResponse)
def update_scene(
    scene_id: int,
    payload: SceneUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> SceneCreateResponse:
    scene = get_scene_or_404(db, scene_id)

    try:
        if payload.name is not None:
            if not payload.name.strip():
                raise HTTPException(status_code=400, detail="场景名称不能为空")
            scene.name = payload.name.strip()
        if payload.description is not None:
            scene.description = payload.description
        if payload.is_active is not None:
            scene.is_active = payload.is_active
        if payload.max_users is not None:
            if payload.max_users < 1:
                raise HTTPException(status_code=400, detail="最大用户数必须大于0")
            scene.max_users = payload.max_users
        if payload.settings is not None:
            scene.settings = payload.settings

        write_audit_log(
            db,
            action="更新协同场景",
            target_type="collaboration_scene",
            target_id=str(scene.id),
            user_id=current_user.id,
        )
        db.commit()

        return SceneCreateResponse(id=scene.id, message="场景更新成功")
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("更新场景失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="更新场景失败")


@router.post("/{scene_id}/join", response_model=SceneJoinResponse)
async def join_scene(
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SceneJoinResponse:
    scene = get_scene_or_404(db, scene_id)

    if not scene.is_active:
        raise_scene_error(
            ErrorCode.SCENE_INACTIVE,
            "场景已关闭，无法加入",
        )

    try:
        active_count = db.query(CollaborationSession).filter(
            CollaborationSession.scene_id == scene_id,
            CollaborationSession.is_active.is_(True),
        ).count()
        if active_count >= scene.max_users:
            raise_scene_error(
                ErrorCode.SCENE_FULL,
                f"场景已满员 (最大 {scene.max_users} 人)",
                {"max_users": scene.max_users, "active_users": active_count},
            )

        existing = db.query(CollaborationSession).filter(
            CollaborationSession.scene_id == scene_id,
            CollaborationSession.user_id == current_user.id,
            CollaborationSession.is_active.is_(True),
        ).first()
        if existing:
            return SceneJoinResponse(
                session_token=existing.session_token,
                scene=get_scene(scene_id, db, current_user),
                message="已重新连接到场景",
            )

        session_token = secrets.token_urlsafe(32)
        session = CollaborationSession(
            scene_id=scene_id,
            user_id=current_user.id,
            session_token=session_token,
            is_active=True,
        )
        db.add(session)

        write_audit_log(
            db,
            action="加入协同场景",
            target_type="collaboration_scene",
            target_id=str(scene_id),
            user_id=current_user.id,
        )
        db.commit()

        return SceneJoinResponse(
            session_token=session_token,
            scene=get_scene(scene_id, db, current_user),
            message="成功加入场景",
        )
    except SceneException:
        raise
    except SQLAlchemyError:
        logger.exception("加入场景失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="加入场景失败")


@router.post("/{scene_id}/leave")
async def leave_scene(
    scene_id: int,
    session_token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = get_session_or_404(db, session_token, current_user.id)

    try:
        session.is_active = False
        session.left_at = datetime.utcnow()

        write_audit_log(
            db,
            action="离开协同场景",
            target_type="collaboration_scene",
            target_id=str(scene_id),
            user_id=current_user.id,
        )
        db.commit()

        return {"message": "已离开场景"}
    except SQLAlchemyError:
        logger.exception("离开场景失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="离开场景失败")


@router.post("/{scene_id}/pointclouds", response_model=dict)
def add_pointcloud_to_scene(
    scene_id: int,
    payload: ScenePointCloudAddRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> dict:
    scene = get_scene_or_404(db, scene_id)

    pointcloud = db.query(PointCloud).filter(PointCloud.id == payload.pointcloud_id).first()
    if not pointcloud:
        raise HTTPException(status_code=404, detail="点云不存在")

    if pointcloud.is_deleted:
        raise HTTPException(status_code=400, detail="点云已被删除，无法添加")

    existing = db.query(ScenePointCloud).filter(
        ScenePointCloud.scene_id == scene_id,
        ScenePointCloud.pointcloud_id == payload.pointcloud_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="点云已在场景中")

    try:
        max_order = db.query(ScenePointCloud).filter(
            ScenePointCloud.scene_id == scene_id,
        ).count()

        spc = ScenePointCloud(
            scene_id=scene_id,
            pointcloud_id=payload.pointcloud_id,
            transform_matrix=payload.transform_matrix,
            visible=payload.visible if payload.visible is not None else True,
            color=payload.color,
            opacity=payload.opacity if payload.opacity is not None else 1.0,
            order=max_order,
            added_by=current_user.id,
        )
        db.add(spc)

        write_audit_log(
            db,
            action="添加点云到场景",
            target_type="scene_pointcloud",
            target_id=str(scene_id),
            user_id=current_user.id,
            detail={"pointcloud_id": payload.pointcloud_id},
        )
        db.commit()

        return {"id": spc.id, "message": "点云已添加到场景"}
    except SQLAlchemyError:
        logger.exception("添加点云到场景失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="添加点云到场景失败")


@router.put("/{scene_id}/pointclouds/{spc_id}", response_model=dict)
def update_scene_pointcloud(
    scene_id: int,
    spc_id: int,
    payload: ScenePointCloudUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> dict:
    spc = db.query(ScenePointCloud).filter(
        ScenePointCloud.id == spc_id,
        ScenePointCloud.scene_id == scene_id,
    ).first()
    if not spc:
        raise HTTPException(status_code=404, detail="场景点云不存在")

    try:
        if payload.transform_matrix is not None:
            spc.transform_matrix = payload.transform_matrix
        if payload.visible is not None:
            spc.visible = payload.visible
        if payload.color is not None:
            spc.color = payload.color
        if payload.opacity is not None:
            if not 0 <= payload.opacity <= 1:
                raise HTTPException(status_code=400, detail="透明度必须在 0-1 范围内")
            spc.opacity = payload.opacity

        db.commit()
        return {"message": "更新成功"}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("更新场景点云失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="更新场景点云失败")


@router.delete("/{scene_id}/pointclouds/{spc_id}")
def remove_pointcloud_from_scene(
    scene_id: int,
    spc_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> dict:
    spc = db.query(ScenePointCloud).filter(
        ScenePointCloud.id == spc_id,
        ScenePointCloud.scene_id == scene_id,
    ).first()
    if not spc:
        raise HTTPException(status_code=404, detail="场景点云不存在")

    try:
        db.delete(spc)

        write_audit_log(
            db,
            action="从场景移除点云",
            target_type="scene_pointcloud",
            target_id=str(spc_id),
            user_id=current_user.id,
        )
        db.commit()

        return {"message": "点云已从场景移除"}
    except SQLAlchemyError:
        logger.exception("移除场景点云失败")
        db.rollback()
        raise HTTPException(status_code=500, detail="移除场景点云失败")


@router.websocket("/ws/{scene_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    scene_id: int,
    session_token: str,
    db: Session = Depends(get_db),
) -> None:
    session = None
    user = None

    try:
        session = db.query(CollaborationSession).filter(
            CollaborationSession.session_token == session_token,
            CollaborationSession.scene_id == scene_id,
            CollaborationSession.is_active.is_(True),
        ).first()
        if not session:
            await websocket.close(code=4004, reason="无效的会话")
            return

        user = db.query(User).filter(User.id == session.user_id).first()
        if not user:
            await websocket.close(code=4004, reason="用户不存在")
            return

        await manager.connect(websocket, scene_id, user.id, session_token)

        await manager.broadcast_to_scene(
            scene_id,
            {
                "event_type": "user_joined",
                "scene_id": scene_id,
                "user_id": user.id,
                "username": user.username,
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude=websocket,
        )

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
            except asyncio.TimeoutError:
                await manager.send_personal(websocket, {"event_type": "ping"})
                continue

            try:
                message = json.loads(data)
                event_type = message.get("event_type")

                if event_type == "camera_update":
                    camera_position = message.get("camera_position")
                    camera_target = message.get("camera_target")
                    session.camera_position = camera_position
                    session.camera_target = camera_target
                    session.last_activity = datetime.utcnow()
                    db.commit()

                    await manager.broadcast_to_scene(
                        scene_id,
                        {
                            "event_type": "camera_update",
                            "scene_id": scene_id,
                            "user_id": user.id,
                            "username": user.username,
                            "camera_position": camera_position,
                            "camera_target": camera_target,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        exclude=websocket,
                    )

                elif event_type == "pointcloud_update":
                    await manager.broadcast_to_scene(
                        scene_id,
                        {
                            "event_type": "pointcloud_update",
                            "scene_id": scene_id,
                            "user_id": user.id,
                            "username": user.username,
                            "data": message.get("data"),
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        exclude=websocket,
                    )

                elif event_type == "task_completed":
                    await manager.broadcast_to_scene(
                        scene_id,
                        {
                            "event_type": "task_completed",
                            "scene_id": scene_id,
                            "user_id": user.id,
                            "username": user.username,
                            "data": message.get("data"),
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )

                elif event_type == "ping":
                    await manager.send_personal(websocket, {"event_type": "pong"})

            except json.JSONDecodeError:
                await manager.send_personal(websocket, {
                    "event_type": "error",
                    "code": ErrorCode.WEBSOCKET_INVALID_MESSAGE.value,
                    "message": "无效的JSON格式",
                })
            except Exception as e:
                logger.exception("WebSocket消息处理失败")
                await manager.send_personal(websocket, {
                    "event_type": "error",
                    "message": f"消息处理失败: {str(e)}",
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket错误")
    finally:
        if session and user:
            manager.disconnect(websocket, scene_id, session_token)
            try:
                session.is_active = False
                session.left_at = datetime.utcnow()
                db.commit()

                await manager.broadcast_to_scene(
                    scene_id,
                    {
                        "event_type": "user_left",
                        "scene_id": scene_id,
                        "user_id": user.id,
                        "username": user.username,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            except Exception:
                logger.exception("清理会话失败")


def get_scene(scene_id: int, db: Session, current_user: User) -> SceneDetail:
    return get_scene(scene_id, db, current_user)
