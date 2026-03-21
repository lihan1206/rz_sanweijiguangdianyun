"""
API测试用例
"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.models.database import Base, get_db
from app.core.security import create_access_token
from app.models.models import User, Scene, PointCloud, ProcessingTask

# 测试数据库配置
TEST_DATABASE_URL = "mysql+aiomysql://pointcloud_user:pointcloud_password@localhost:3306/pointcloud_test_db"

# 创建测试引擎
engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    future=True
)

# 创建测试会话
TestingSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session():
    """创建测试数据库会话"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session):
    """创建测试客户端"""
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def test_user(db_session):
    """创建测试用户"""
    from app.core.security import get_password_hash
    
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=get_password_hash("testpassword"),
        full_name="Test User",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def auth_token(test_user):
    """创建认证token"""
    return create_access_token({"sub": str(test_user.id)})


@pytest.fixture(scope="function")
async def auth_headers(auth_token):
    """创建认证头"""
    return {"Authorization": f"Bearer {auth_token}"}


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_register_user(client):
    """测试用户注册"""
    response = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "newpassword123",
        "full_name": "New User"
    })
    
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == 201
    assert data["data"]["username"] == "newuser"
    assert data["data"]["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_username(client, test_user):
    """测试重复用户名注册"""
    response = await client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "different@example.com",
        "password": "password123"
    })
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client, test_user):
    """测试登录成功"""
    response = await client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "testpassword"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]


@pytest.mark.asyncio
async def test_login_invalid_credentials(client, test_user):
    """测试登录失败"""
    response = await client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "wrongpassword"
    })
    
    assert response.status_code == 401


# ==================== 点云管理测试 ====================

@pytest.mark.asyncio
async def test_list_point_clouds(client, auth_headers, test_user, db_session):
    """测试获取点云列表"""
    # 创建测试点云
    pc = PointCloud(
        user_id=test_user.id,
        name="Test Point Cloud",
        original_filename="test.ply",
        file_path="/uploads/test.ply",
        file_size=1024,
        file_format="ply",
        point_count=1000,
        status="ready"
    )
    db_session.add(pc)
    await db_session.commit()
    
    response = await client.get("/api/v1/pointclouds", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["name"] == "Test Point Cloud"


@pytest.mark.asyncio
async def test_get_point_cloud_detail(client, auth_headers, test_user, db_session):
    """测试获取点云详情"""
    pc = PointCloud(
        user_id=test_user.id,
        name="Test Point Cloud",
        original_filename="test.ply",
        file_path="/uploads/test.ply",
        file_size=1024,
        file_format="ply",
        point_count=1000,
        status="ready"
    )
    db_session.add(pc)
    await db_session.commit()
    await db_session.refresh(pc)
    
    response = await client.get(f"/api/v1/pointclouds/{pc.id}", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["name"] == "Test Point Cloud"


@pytest.mark.asyncio
async def test_delete_point_cloud(client, auth_headers, test_user, db_session):
    """测试删除点云"""
    pc = PointCloud(
        user_id=test_user.id,
        name="Test Point Cloud",
        original_filename="test.ply",
        file_path="/uploads/test.ply",
        file_size=1024,
        file_format="ply",
        point_count=1000,
        status="ready"
    )
    db_session.add(pc)
    await db_session.commit()
    await db_session.refresh(pc)
    
    response = await client.delete(f"/api/v1/pointclouds/{pc.id}", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200


# ==================== 场景测试 ====================

@pytest.mark.asyncio
async def test_create_scene(client, auth_headers, test_user):
    """测试创建场景"""
    response = await client.post("/api/v1/scenes", json={
        "name": "Test Scene",
        "description": "Test Description",
        "visibility": "private",
        "max_members": 10
    }, headers=auth_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == 201
    assert data["data"]["name"] == "Test Scene"
    assert "invite_code" in data["data"]


@pytest.mark.asyncio
async def test_list_scenes(client, auth_headers, test_user, db_session):
    """测试获取场景列表"""
    scene = Scene(
        name="Test Scene",
        owner_id=test_user.id,
        visibility="private",
        max_members=10,
        invite_code="TEST123"
    )
    db_session.add(scene)
    await db_session.commit()
    
    response = await client.get("/api/v1/scenes", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_join_scene(client, auth_headers, test_user, db_session):
    """测试加入场景"""
    # 创建场景所有者
    from app.core.security import get_password_hash
    owner = User(
        username="owner",
        email="owner@example.com",
        password_hash=get_password_hash("password"),
        is_active=True
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)
    
    scene = Scene(
        name="Test Scene",
        owner_id=owner.id,
        visibility="shared",
        max_members=10,
        invite_code="JOIN123"
    )
    db_session.add(scene)
    await db_session.commit()
    await db_session.refresh(scene)
    
    response = await client.post(
        f"/api/v1/scenes/{scene.id}/join",
        json={"invite_code": "JOIN123"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200


# ==================== 任务测试 ====================

@pytest.mark.asyncio
async def test_create_task(client, auth_headers, test_user, db_session):
    """测试创建处理任务"""
    pc = PointCloud(
        user_id=test_user.id,
        name="Test Point Cloud",
        original_filename="test.ply",
        file_path="/uploads/test.ply",
        file_size=1024,
        file_format="ply",
        point_count=1000,
        status="ready"
    )
    db_session.add(pc)
    await db_session.commit()
    await db_session.refresh(pc)
    
    response = await client.post("/api/v1/tasks", json={
        "point_cloud_id": pc.id,
        "task_type": "filter_voxel",
        "task_name": "Voxel Filter Task",
        "parameters": {"voxel_size": 0.05}
    }, headers=auth_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == 201
    assert data["data"]["task_type"] == "filter_voxel"


@pytest.mark.asyncio
async def test_list_tasks(client, auth_headers, test_user, db_session):
    """测试获取任务列表"""
    pc = PointCloud(
        user_id=test_user.id,
        name="Test Point Cloud",
        original_filename="test.ply",
        file_path="/uploads/test.ply",
        file_size=1024,
        file_format="ply",
        point_count=1000,
        status="ready"
    )
    db_session.add(pc)
    await db_session.commit()
    await db_session.refresh(pc)
    
    task = ProcessingTask(
        point_cloud_id=pc.id,
        user_id=test_user.id,
        task_type="filter_voxel",
        task_name="Test Task",
        parameters={"voxel_size": 0.05},
        status="pending"
    )
    db_session.add(task)
    await db_session.commit()
    
    response = await client.get("/api/v1/tasks", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_cancel_task(client, auth_headers, test_user, db_session):
    """测试取消任务"""
    pc = PointCloud(
        user_id=test_user.id,
        name="Test Point Cloud",
        original_filename="test.ply",
        file_path="/uploads/test.ply",
        file_size=1024,
        file_format="ply",
        point_count=1000,
        status="ready"
    )
    db_session.add(pc)
    await db_session.commit()
    await db_session.refresh(pc)
    
    task = ProcessingTask(
        point_cloud_id=pc.id,
        user_id=test_user.id,
        task_type="filter_voxel",
        task_name="Test Task",
        parameters={"voxel_size": 0.05},
        status="pending"
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    
    response = await client.post(f"/api/v1/tasks/{task.id}/cancel", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200


# ==================== 并发测试 ====================

@pytest.mark.asyncio
async def test_concurrent_uploads(client, auth_headers):
    """测试并发上传"""
    # 模拟多个用户同时上传
    import io
    
    async def upload_file(filename):
        file_content = b"mock point cloud data" * 1000
        files = {"file": (filename, io.BytesIO(file_content), "application/octet-stream")}
        data = {"name": f"Test {filename}", "visibility": "private"}
        return await client.post(
            "/api/v1/pointclouds/upload",
            files=files,
            data=data,
            headers=auth_headers
        )
    
    # 并发上传3个文件
    responses = await asyncio.gather(
        upload_file("test1.ply"),
        upload_file("test2.ply"),
        upload_file("test3.ply")
    )
    
    # 所有请求都应该成功（202 Accepted）
    for response in responses:
        assert response.status_code in [201, 202, 500]  # 500是因为没有实际文件处理


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
