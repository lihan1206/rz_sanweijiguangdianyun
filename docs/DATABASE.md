# 数据库表结构设计

## ER 图

```
┌─────────────────────┐
│       users         │
├─────────────────────┤
│ PK  id              │
│     username        │
│     password_hash   │
│     role            │
│     is_active       │
│     created_at      │
│     updated_at      │
└─────────┬───────────┘
          │
          │ 1:N
          │
          ├──────────────────────────────────────────────────────┐
          │                                                      │
          ▼                                                      ▼
┌─────────────────────┐                              ┌─────────────────────┐
│    pointclouds      │                              │ collaboration_scenes│
├─────────────────────┤                              ├─────────────────────┤
│ PK  id              │                              │ PK  id              │
│     name            │                              │     name            │
│     original_filename│                              │     description     │
│     storage_path    │                              │     is_active       │
│     file_format     │                              │     max_users       │
│     file_size       │                              │     settings        │
│     points_count    │                              │ FK  created_by      │
│     capture_time    │                              │     created_at      │
│     sensor_model    │                              │     updated_at      │
│     coordinate_system│                              └─────────┬───────────┘
│     bounding_box    │                                        │
│     group_name      │                                        │ 1:N
│     tags            │                                        │
│     version         │                                        │
│     is_archived     │                                        │
│     is_deleted      │                                        │
│     deleted_at      │                                        │
│ FK  created_by      │                                        │
│     created_at      │                                        │
│     updated_at      │                                        │
└─────────┬───────────┘                                        │
          │                                                    │
          │ 1:N                                                │
          │                                                    │
          ▼                                                    │
┌─────────────────────┐                              ┌─────────▼───────────┐
│  processing_tasks   │                              │ scene_pointclouds   │
├─────────────────────┤                              ├─────────────────────┤
│ PK  id              │                              │ PK  id              │
│ FK  pointcloud_id   │◄─────────────────────────────│ FK  scene_id        │
│ FK  scene_id        │──────────────────────────────│ FK  pointcloud_id   │
│     task_type       │                              │     transform_matrix│
│     parameters      │                              │     visible         │
│     status          │                              │     color           │
│ FK  result_pointcloud│                              │     opacity         │
│     output_format   │                              │     order           │
│     error_message   │                              │ FK  added_by        │
│     progress        │                              │     added_at        │
│ FK  created_by      │                              └─────────────────────┘
│     created_at      │
│     updated_at      │                              ┌─────────────────────┐
│     finished_at     │                              │ collaboration_sessions│
└─────────────────────┘                              ├─────────────────────┤
                                                     │ PK  id              │
          ┌──────────────────────────────────────────│ FK  scene_id        │
          │                                          │ FK  user_id         │
          │ 1:N                                      │     session_token   │
          │                                          │     camera_position │
          ▼                                          │     camera_target   │
┌─────────────────────┐                              │     is_active       │
│     audit_logs      │                              │     last_activity   │
├─────────────────────┤                              │     joined_at       │
│ PK  id              │                              │     left_at         │
│ FK  user_id         │                              └─────────────────────┘
│     action          │
│     target_type     │
│     target_id       │
│     detail          │
│     created_at      │
└─────────────────────┘
```

## 表结构详细设计

### 1. users (用户表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 用户ID |
| username | VARCHAR(64) | UNIQUE, NOT NULL | 用户名 |
| password_hash | VARCHAR(255) | NOT NULL | 密码哈希 |
| role | ENUM | NOT NULL, DEFAULT 'viewer' | 角色: admin, engineer, viewer |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | 是否启用 |
| created_at | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| updated_at | DATETIME | NOT NULL, ON UPDATE NOW | 更新时间 |

### 2. pointclouds (点云表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 点云ID |
| name | VARCHAR(128) | NOT NULL | 点云名称 |
| original_filename | VARCHAR(255) | NOT NULL | 原始文件名 |
| storage_path | VARCHAR(255) | NOT NULL | 存储路径 |
| file_format | VARCHAR(16) | NOT NULL | 文件格式 |
| file_size | INT | NOT NULL | 文件大小(字节) |
| points_count | INT | NULL | 点数量 |
| capture_time | DATETIME | NULL | 采集时间 |
| sensor_model | VARCHAR(128) | NULL | 传感器型号 |
| coordinate_system | VARCHAR(128) | NULL | 坐标系 |
| bounding_box | JSON | NULL | 包围盒 |
| group_name | VARCHAR(64) | NULL | 分组名称 |
| tags | JSON | NULL | 标签数组 |
| version | INT | NOT NULL, DEFAULT 1 | 版本号 |
| is_archived | BOOLEAN | NOT NULL, DEFAULT FALSE | 是否归档 |
| is_deleted | BOOLEAN | NOT NULL, DEFAULT FALSE | 是否删除 |
| deleted_at | DATETIME | NULL | 删除时间 |
| created_by | INT | FK, NOT NULL | 创建者ID |
| created_at | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| updated_at | DATETIME | NOT NULL, ON UPDATE NOW | 更新时间 |

### 3. processing_tasks (处理任务表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 任务ID |
| pointcloud_id | INT | FK, NOT NULL | 源点云ID |
| scene_id | INT | FK, NULL | 关联场景ID |
| task_type | ENUM | NOT NULL | 任务类型 |
| parameters | JSON | NULL | 处理参数 |
| status | ENUM | NOT NULL, DEFAULT 'pending' | 状态: pending, running, success, failed |
| result_pointcloud_id | INT | FK, NULL | 结果点云ID |
| output_format | VARCHAR(16) | NOT NULL, DEFAULT 'ply' | 输出格式 |
| error_message | TEXT | NULL | 错误信息 |
| progress | INT | NOT NULL, DEFAULT 0 | 进度(0-100) |
| created_by | INT | FK, NOT NULL | 创建者ID |
| created_at | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| updated_at | DATETIME | NOT NULL, ON UPDATE NOW | 更新时间 |
| finished_at | DATETIME | NULL | 完成时间 |

### 4. collaboration_scenes (协同场景表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 场景ID |
| name | VARCHAR(128) | NOT NULL | 场景名称 |
| description | TEXT | NULL | 场景描述 |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | 是否活跃 |
| max_users | INT | NOT NULL, DEFAULT 10 | 最大用户数 |
| settings | JSON | NULL | 场景设置 |
| created_by | INT | FK, NOT NULL | 创建者ID |
| created_at | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| updated_at | DATETIME | NOT NULL, ON UPDATE NOW | 更新时间 |

### 5. scene_pointclouds (场景点云关联表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 记录ID |
| scene_id | INT | FK, NOT NULL | 场景ID |
| pointcloud_id | INT | FK, NOT NULL | 点云ID |
| transform_matrix | JSON | NULL | 变换矩阵 |
| visible | BOOLEAN | NOT NULL, DEFAULT TRUE | 是否可见 |
| color | VARCHAR(32) | NULL | 显示颜色 |
| opacity | DOUBLE | NOT NULL, DEFAULT 1.0 | 透明度 |
| order | INT | NOT NULL, DEFAULT 0 | 显示顺序 |
| added_by | INT | FK, NOT NULL | 添加者ID |
| added_at | DATETIME | NOT NULL, DEFAULT NOW | 添加时间 |

**唯一约束**: (scene_id, pointcloud_id)

### 6. collaboration_sessions (协同会话表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 会话ID |
| scene_id | INT | FK, NOT NULL | 场景ID |
| user_id | INT | FK, NOT NULL | 用户ID |
| session_token | VARCHAR(64) | UNIQUE, NOT NULL | 会话令牌 |
| camera_position | JSON | NULL | 相机位置 |
| camera_target | JSON | NULL | 相机目标 |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | 是否活跃 |
| last_activity | DATETIME | NOT NULL, DEFAULT NOW | 最后活动时间 |
| joined_at | DATETIME | NOT NULL, DEFAULT NOW | 加入时间 |
| left_at | DATETIME | NULL | 离开时间 |

**索引**:
- idx_session_token (session_token)
- idx_active_sessions (scene_id, is_active)

### 7. audit_logs (审计日志表)

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PK, AUTO_INCREMENT | 日志ID |
| user_id | INT | FK, NULL | 用户ID |
| action | VARCHAR(255) | NOT NULL | 操作动作 |
| target_type | VARCHAR(64) | NOT NULL | 目标类型 |
| target_id | VARCHAR(64) | NOT NULL | 目标ID |
| detail | JSON | NULL | 详情 |
| created_at | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |

## 索引设计

### 主键索引
- 所有表的 id 字段

### 外键索引
- pointclouds.created_by → users.id
- processing_tasks.pointcloud_id → pointclouds.id
- processing_tasks.result_pointcloud_id → pointclouds.id
- processing_tasks.scene_id → collaboration_scenes.id
- processing_tasks.created_by → users.id
- collaboration_scenes.created_by → users.id
- scene_pointclouds.scene_id → collaboration_scenes.id
- scene_pointclouds.pointcloud_id → pointclouds.id
- scene_pointclouds.added_by → users.id
- collaboration_sessions.scene_id → collaboration_scenes.id
- collaboration_sessions.user_id → users.id
- audit_logs.user_id → users.id

### 业务索引
- users.username (唯一索引)
- pointclouds.created_by
- pointclouds.group_name
- processing_tasks.status
- collaboration_sessions.session_token (唯一索引)
- collaboration_sessions(scene_id, is_active) (复合索引)
