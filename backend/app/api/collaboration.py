from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.models.collaboration import CollaborativeSession, SessionParticipant
from app.models.user import User, UserRole
from app.schemas.collaboration import (
    CollaborativeSession as SessionSchema,
    CollaborativeSessionCreate,
    CollaborativeSessionUpdate,
    JoinSessionRequest,
    SessionUserInfo,
)

router = APIRouter(prefix="/collaboration", tags=["协同处理"])
settings = get_settings()

# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}  # session_id -> connections

    async def connect(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: int):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast(self, message: dict, session_id: int):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                await connection.send_json(message)

manager = ConnectionManager()


@router.get("/sessions", response_model=List[SessionSchema])
def list_sessions(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[SessionSchema]:
    """获取所有协同会话列表"""
    query = db.query(CollaborativeSession)
    if not include_inactive:
        query = query.filter(CollaborativeSession.is_active.is_(True))
    sessions = query.order_by(CollaborativeSession.created_at.desc()).all()
    return [SessionSchema.model_validate(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=SessionSchema)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SessionSchema:
    """获取单个会话详情"""
    session = db.query(CollaborativeSession).filter(
        CollaborativeSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="协同会话不存在")
    return SessionSchema.model_validate(session)


@router.post("/sessions", response_model=SessionSchema)
def create_session(
    payload: CollaborativeSessionCreate,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> SessionSchema:
    """创建新的协同会话"""
    session = CollaborativeSession(
        session_name=payload.session_name,
        description=payload.description,
        max_users=payload.max_users,
        created_by=current_user.id,
        is_active=True,
        current_users=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionSchema.model_validate(session)


@router.put("/sessions/{session_id}", response_model=SessionSchema)
def update_session(
    session_id: int,
    payload: CollaborativeSessionUpdate,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.ENGINEER)),
    db: Session = Depends(get_db),
) -> SessionSchema:
    """更新协同会话"""
    session = db.query(CollaborativeSession).filter(
        CollaborativeSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="协同会话不存在")
    
    if session.created_by != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="无权限修改此会话")

    for key, value in payload.dict(exclude_unset=True).items():
        setattr(session, key, value)
    
    db.commit()
    db.refresh(session)
    return SessionSchema.model_validate(session)


@router.post("/join", response_model=SessionSchema)
def join_session(
    payload: JoinSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionSchema:
    """加入协同会话"""
    session = db.query(CollaborativeSession).filter(
        CollaborativeSession.id == payload.session_id,
        CollaborativeSession.is_active.is_(True),
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="协同会话不存在或已关闭")
    
    if session.current_users >= session.max_users:
        raise HTTPException(status_code=400, detail="会话用户数已达上限")
    
    # 检查是否已加入
    existing = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == payload.session_id,
        SessionParticipant.user_id == current_user.id,
    ).first()
    
    if existing:
        existing.is_online = True
        existing.last_active = datetime.utcnow()
    else:
        participant = SessionParticipant(
            session_id=payload.session_id,
            user_id=current_user.id,
            is_online=True,
        )
        db.add(participant)
        session.current_users += 1
    
    db.commit()
    db.refresh(session)
    return SessionSchema.model_validate(session)


@router.post("/leave/{session_id}")
def leave_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """离开协同会话"""
    participant = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_id,
        SessionParticipant.user_id == current_user.id,
    ).first()
    
    if participant:
        participant.is_online = False
        participant.last_active = datetime.utcnow()
        
        session = db.query(CollaborativeSession).filter(
            CollaborativeSession.id == session_id
        ).first()
        if session:
            session.current_users = max(0, session.current_users - 1)
        
        db.commit()
    
    return {"message": "已离开会话"}


@router.get("/sessions/{session_id}/users", response_model=List[SessionUserInfo])
def get_session_users(
    session_id: int,
    online_only: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[SessionUserInfo]:
    """获取会话中的用户列表"""
    query = db.query(
        SessionParticipant,
        User.username,
        User.role,
    ).join(
        User, SessionParticipant.user_id == User.id
    ).filter(
        SessionParticipant.session_id == session_id
    )
    
    if online_only:
        query = query.filter(SessionParticipant.is_online.is_(True))
    
    results = query.all()
    return [
        SessionUserInfo(
            user_id=participant.user_id,
            username=username,
            role=role,
            is_online=participant.is_online,
            joined_at=participant.joined_at,
        )
        for participant, username, role in results
    ]


@router.get("/my-sessions", response_model=List[SessionSchema])
def get_my_sessions(
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[SessionSchema]:
    """获取我参与的会话"""
    query = db.query(CollaborativeSession).join(
        SessionParticipant,
        CollaborativeSession.id == SessionParticipant.session_id
    ).filter(
        SessionParticipant.user_id == current_user.id
    )
    
    if active_only:
        query = query.filter(CollaborativeSession.is_active.is_(True))
    
    sessions = query.order_by(CollaborativeSession.created_at.desc()).all()
    return [SessionSchema.model_validate(session) for session in sessions]


# WebSocket 实时协同
@router.websocket("/ws/{session_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: int,
    user_id: int,
):
    """WebSocket实时协同通信端点"""
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            # 广播消息给同会话的其他用户
            await manager.broadcast({
                **data,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            }, session_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        # 通知其他用户有人离开
        await manager.broadcast({
            "type": "user_left",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }, session_id)
