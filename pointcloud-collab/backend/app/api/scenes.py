from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.scene import Scene, SceneMember, SceneVisibility, SceneMemberRole
from app.models.point_cloud import PointCloud, PointCloudVisibility
from app.models.user import User
from app.utils.schemas import (
    ResponseBase, SceneCreate, SceneUpdate, SceneResponse, SceneListResponse,
    JoinSceneRequest, SceneMemberResponse, SceneDataResponse,
    PaginationParams
)

router = APIRouter(prefix="/scenes", tags=["Scenes"])


@router.post("", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_scene(
    scene_data: SceneCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """创建场景"""
    # 生成邀请码
    import secrets
    import string
    
    invite_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    
    # 创建场景
    scene = Scene(
        name=scene_data.name,
        description=scene_data.description,
        owner_id=user_id,
        visibility=scene_data.visibility,
        max_members=scene_data.max_members,
        invite_code=invite_code
    )
    
    db.add(scene)
    await db.flush()
    
    # 创建者自动成为成员
    member = SceneMember(
        scene_id=scene.id,
        user_id=user_id,
        role=SceneMemberRole.OWNER
    )
    db.add(member)
    
    await db.commit()
    await db.refresh(scene)
    
    return ResponseBase(
        code=201,
        message="Scene created",
        data=scene.to_dict(include_owner=True)
    )


@router.get("", response_model=ResponseBase)
async def list_scenes(
    owned: Optional[bool] = None,
    joined: Optional[bool] = None,
    params: PaginationParams = Depends(),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取场景列表"""
    # 构建查询
    if owned:
        # 只显示我创建的
        query = select(Scene).where(Scene.owner_id == user_id)
    elif joined:
        # 只显示我加入的（不包括自己创建的）
        query = (
            select(Scene)
            .join(SceneMember, Scene.id == SceneMember.scene_id)
            .where(
                and_(
                    SceneMember.user_id == user_id,
                    Scene.owner_id != user_id
                )
            )
        )
    else:
        # 显示所有我有权限访问的
        query = (
            select(Scene)
            .outerjoin(SceneMember, Scene.id == SceneMember.scene_id)
            .where(
                or_(
                    Scene.owner_id == user_id,
                    SceneMember.user_id == user_id,
                    Scene.visibility == SceneVisibility.PUBLIC
                )
            )
            .distinct()
        )
    
    # 排序
    query = query.order_by(desc(Scene.created_at))
    
    # 分页
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()
    
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    
    result = await db.execute(query)
    scenes = result.scalars().all()
    
    return ResponseBase(
        code=200,
        data={
            "items": [scene.to_dict(include_owner=True, include_stats=True) for scene in scenes],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "pages": (total + params.page_size - 1) // params.page_size
        }
    )


@router.get("/{scene_id}", response_model=ResponseBase)
async def get_scene(
    scene_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取场景详情"""
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # 检查权限
    if scene.visibility == SceneVisibility.PRIVATE and scene.owner_id != user_id:
        # 检查是否是成员
        result = await db.execute(
            select(SceneMember).where(
                and_(SceneMember.scene_id == scene_id, SceneMember.user_id == user_id)
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    return ResponseBase(
        code=200,
        data=scene.to_dict(include_owner=True, include_stats=True)
    )


@router.put("/{scene_id}", response_model=ResponseBase)
async def update_scene(
    scene_id: int,
    scene_data: SceneUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """更新场景"""
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # 检查权限（只有所有者可以修改）
    if scene.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can update scene"
        )
    
    # 更新字段
    if scene_data.name is not None:
        scene.name = scene_data.name
    if scene_data.description is not None:
        scene.description = scene_data.description
    if scene_data.visibility is not None:
        scene.visibility = scene_data.visibility
    if scene_data.max_members is not None:
        scene.max_members = scene_data.max_members
    
    await db.commit()
    await db.refresh(scene)
    
    return ResponseBase(
        code=200,
        message="Scene updated",
        data=scene.to_dict(include_owner=True, include_stats=True)
    )


@router.delete("/{scene_id}", response_model=ResponseBase)
async def delete_scene(
    scene_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """删除场景"""
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # 检查权限（只有所有者可以删除）
    if scene.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can delete scene"
        )
    
    await db.delete(scene)
    await db.commit()
    
    return ResponseBase(
        code=200,
        message="Scene deleted"
    )


@router.post("/{scene_id}/join", response_model=ResponseBase)
async def join_scene(
    scene_id: int,
    join_data: JoinSceneRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """加入场景"""
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # 验证邀请码
    if scene.invite_code != join_data.invite_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invite code"
        )
    
    # 检查是否已经是成员
    result = await db.execute(
        select(SceneMember).where(
            and_(SceneMember.scene_id == scene_id, SceneMember.user_id == user_id)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already a member of this scene"
        )
    
    # 检查成员数量
    result = await db.execute(
        select(func.count()).where(SceneMember.scene_id == scene_id)
    )
    member_count = result.scalar()
    if member_count >= scene.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scene is full"
        )
    
    # 添加成员
    member = SceneMember(
        scene_id=scene_id,
        user_id=user_id,
        role=SceneMemberRole.VIEWER
    )
    db.add(member)
    await db.commit()
    
    return ResponseBase(
        code=200,
        message="Joined scene successfully"
    )


@router.post("/{scene_id}/leave", response_model=ResponseBase)
async def leave_scene(
    scene_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """离开场景"""
    result = await db.execute(
        select(SceneMember).where(
            and_(SceneMember.scene_id == scene_id, SceneMember.user_id == user_id)
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not a member of this scene"
        )
    
    # 所有者不能离开，只能删除场景
    if member.role == SceneMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot leave scene. Delete the scene instead."
        )
    
    await db.delete(member)
    await db.commit()
    
    return ResponseBase(
        code=200,
        message="Left scene successfully"
    )


@router.get("/{scene_id}/members", response_model=ResponseBase)
async def get_scene_members(
    scene_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取场景成员列表"""
    # 检查场景是否存在
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # 检查权限
    if scene.visibility == SceneVisibility.PRIVATE:
        result = await db.execute(
            select(SceneMember).where(
                and_(SceneMember.scene_id == scene_id, SceneMember.user_id == user_id)
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    # 获取成员列表
    result = await db.execute(
        select(SceneMember, User)
        .join(User, SceneMember.user_id == User.id)
        .where(SceneMember.scene_id == scene_id)
    )
    members = result.all()
    
    return ResponseBase(
        code=200,
        data={
            "members": [
                {
                    "id": member.SceneMember.id,
                    "scene_id": member.SceneMember.scene_id,
                    "user_id": member.SceneMember.user_id,
                    "role": member.SceneMember.role.value,
                    "permissions": member.SceneMember.permissions,
                    "joined_at": member.SceneMember.joined_at.isoformat() if member.SceneMember.joined_at else None,
                    "last_active": member.SceneMember.last_active.isoformat() if member.SceneMember.last_active else None,
                    "user": {
                        "id": member.User.id,
                        "username": member.User.username,
                        "full_name": member.User.full_name,
                        "avatar_url": member.User.avatar_url
                    }
                }
                for member in members
            ]
        }
    )


@router.get("/{scene_id}/pointclouds", response_model=ResponseBase)
async def get_scene_pointclouds(
    scene_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """获取场景中的点云（协同视图）"""
    # 检查场景
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found"
        )
    
    # 检查权限
    result = await db.execute(
        select(SceneMember).where(
            and_(SceneMember.scene_id == scene_id, SceneMember.user_id == user_id)
        )
    )
    is_member = result.scalar_one_or_none() is not None
    
    if scene.visibility == SceneVisibility.PRIVATE and not is_member and scene.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # 获取场景中的点云
    result = await db.execute(
        select(PointCloud, User)
        .join(User, PointCloud.user_id == User.id)
        .where(
            and_(
                PointCloud.scene_id == scene_id,
                PointCloud.status != 'deleted'
            )
        )
    )
    point_clouds = result.all()
    
    return ResponseBase(
        code=200,
        data={
            "scene_id": scene_id,
            "point_clouds": [
                {
                    "id": pc.PointCloud.id,
                    "name": pc.PointCloud.name,
                    "owner": {
                        "id": pc.User.id,
                        "username": pc.User.username
                    },
                    "status": pc.PointCloud.status.value if pc.PointCloud.status else None,
                    "transform": {
                        "position": [0, 0, 0],
                        "rotation": [0, 0, 0],
                        "scale": [1, 1, 1]
                    },
                    "visible": True,
                    "color": "#" + "%06x" % (pc.PointCloud.id * 123456 % 0xFFFFFF)
                }
                for pc in point_clouds
            ],
            "active_users": []  # WebSocket会填充这个
        }
    )
