# 三维激光点云处理平台

## 🛠 技术栈
- Frontend: React 18 + TypeScript + Ant Design + Three.js
- Backend: FastAPI + SQLAlchemy + JWT
- Database: MySQL 8.0

## 🚀 启动指南 (How to Run)
1. 确保 Docker Desktop 已启动。
2. 在根目录执行：`docker compose up --build`
3. 等待容器启动完成（首次构建会下载依赖，耗时较长）。

## 🔗 服务地址 (Services)
- Frontend: [http://localhost:3317](http://localhost:3317)
- Backend Swagger: [http://localhost:8317/docs](http://localhost:8317/docs)
- Backend Health: [http://localhost:8317/health](http://localhost:8317/health)
- Database: `localhost:13306` (user: `appuser` / pass: `app123456`)

## 🧪 测试账号
- 管理员: `admin / 123456`
- 工程师: `engineer / 123456`
- 查看员: `viewer / 123456`

## ✅ 已实现能力
- 点云上传与元数据管理（支持 `las/laz/ply/xyz/e57/csv`）
- 点云软删除与恢复（删除采用 UI 二次确认弹窗）
- 点云处理任务（降采样、去噪、高度裁剪、格式转换）
- 处理结果自动入库并生成新版本点云
- 点云统计分析（点数、密度、XYZ 范围）
- 3D 点云采样预览（Three.js）
- 用户角色权限（管理员/工程师/查看员）
- 审计日志追踪
- 启动自动种子数据（演示点云 + 默认账号）

## 🐳 容器说明
- `db`: MySQL 8.0，挂载 `db_data` 做持久化
- `backend`: FastAPI 服务，挂载 `uploads_data` 做点云文件持久化
- `frontend`: Nginx 托管构建后的前端静态资源

## 📁 目录结构
- `backend/` 后端代码与 Dockerfile
- `frontend/` 前端代码与 Dockerfile
- `mysql-init/` 数据库初始化脚本
- `docker-compose.yml` 一键启动编排文件

## 注意事项
- 本项目核心逻辑不使用 Mock 数据，所有业务数据均写入 MySQL。
- 前端所有用户文案均为中文。
- 当前点云统计/可视化处理接口支持 `xyz/csv/ply` 深度解析；其他格式可上传存档并管理。
