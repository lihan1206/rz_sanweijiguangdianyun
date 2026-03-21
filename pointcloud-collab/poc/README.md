# 点云协同处理系统 - PoC版本

## 概述
这是一个概念验证（PoC）版本，用于快速验证多用户协同点云处理的核心功能。

## 核心功能
- ✅ 多用户同时上传点云文件（.ply, .xyz）
- ✅ 实时协同可视化（WebSocket广播）
- ✅ 基础点云处理（Voxel滤波、RANSAC分割）
- ✅ JWT认证
- ✅ 响应式Web界面

## 技术栈
- **后端**: FastAPI + SQLite（简化数据库）
- **前端**: 单HTML文件 + Three.js
- **点云处理**: Open3D
- **实时通信**: WebSocket

## 快速启动

### 方式1：本地运行
```bash
# 1. 安装依赖
pip install fastapi uvicorn open3d python-jose passlib python-multipart websockets jinja2 aiofiles

# 2. 启动服务
cd poc
python app.py

# 3. 访问 http://localhost:8000
```

### 方式2：Docker运行
```bash
docker-compose up -d
```

## 测试账号
- 用户名: `demo`
- 密码: `demo123`

## 文件结构
```
poc/
├── app.py              # 后端主文件（包含API和WebSocket）
├── index.html          # 前端单页面
├── requirements.txt    # Python依赖
├── Dockerfile          # 容器配置
└── docker-compose.yml  # 一键部署
```

## 限制说明
- 使用SQLite代替MySQL（简化部署）
- 单文件处理（无分片上传）
- 内存存储点云数据（重启后丢失）
- 简化用户管理（无注册，预置账号）
- 无Celery（同步处理任务）

## 验证场景
1. 打开两个浏览器窗口，分别登录
2. 用户A上传点云文件
3. 用户B实时看到上传的点云
4. 用户A执行滤波处理
5. 用户B实时看到处理结果
