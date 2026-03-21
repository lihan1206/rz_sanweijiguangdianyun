# API 接口设计

## 基础信息

- **Base URL**: `/api/v1`
- **认证方式**: JWT Bearer Token
- **响应格式**: JSON

## 1. 认证接口

### 1.1 用户登录
```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

请求参数:
- username: string (必填)
- password: string (必填)

响应:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

### 1.2 获取当前用户信息
```
GET /auth/me
Authorization: Bearer <token>

响应:
{
  "id": 1,
  "username": "admin",
  "role": "admin",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00"
}
```

## 2. 点云管理接口

### 2.1 上传点云文件
```
POST /pointclouds/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

请求参数:
- file: File (必填) - 点云文件 (.ply, .las, .xyz, .csv)
- name: string (必填) - 点云名称
- group_name: string (可选) - 分组名称
- tags: string (可选) - 标签，逗号分隔
- capture_time: string (可选) - 采集时间 ISO格式
- sensor_model: string (可选) - 传感器型号
- coordinate_system: string (可选) - 坐标系

响应:
{
  "id": 1,
  "message": "上传成功"
}
```

### 2.2 获取点云列表
```
GET /pointclouds
Authorization: Bearer <token>

查询参数:
- include_deleted: boolean (默认false)
- group_name: string (可选)
- keyword: string (可选)

响应:
[
  {
    "id": 1,
    "name": "测试点云",
    "original_filename": "test.ply",
    "file_format": "ply",
    "file_size": 1024000,
    "points_count": 100000,
    "group_name": "默认分组",
    "tags": ["测试", "室内"],
    "version": 1,
    "is_archived": false,
    "is_deleted": false,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

### 2.3 获取点云详情
```
GET /pointclouds/{id}
Authorization: Bearer <token>

响应:
{
  "id": 1,
  "name": "测试点云",
  "original_filename": "test.ply",
  "file_format": "ply",
  "file_size": 1024000,
  "points_count": 100000,
  "bounding_box": {
    "x": [0.0, 100.0],
    "y": [0.0, 100.0],
    "z": [0.0, 50.0]
  },
  "group_name": "默认分组",
  "tags": ["测试"],
  "version": 1,
  "created_by": 1,
  "created_at": "2024-01-01T00:00:00"
}
```

### 2.4 获取点云采样数据
```
GET /pointclouds/{id}/sample
Authorization: Bearer <token>

查询参数:
- limit: int (默认3000, 最大50000)

响应:
{
  "points": [
    [1.0, 2.0, 3.0],
    [1.5, 2.5, 3.5],
    ...
  ]
}
```

### 2.5 删除点云（软删除）
```
DELETE /pointclouds/{id}
Authorization: Bearer <token>

响应:
{
  "message": "删除成功，可在回收站恢复"
}
```

### 2.6 恢复点云
```
POST /pointclouds/{id}/restore
Authorization: Bearer <token>

响应:
{
  "message": "恢复成功"
}
```

## 3. 处理任务接口

### 3.1 创建处理任务
```
POST /tasks
Authorization: Bearer <token>

请求体:
{
  "pointcloud_id": 1,
  "scene_id": 1,  // 可选，关联协同场景
  "task_type": "voxel_grid_filter",
  "parameters": {
    "voxel_size": 0.05
  },
  "output_format": "ply"
}

任务类型 (task_type):
- downsample: 降采样
- denoise: 去噪
- clip_z: 高度裁剪
- format_convert: 格式转换
- voxel_grid_filter: 体素网格滤波
- statistical_outlier_removal: 统计离群点移除
- ransac_plane_segmentation: RANSAC平面分割
- icp_registration: ICP配准
- ai_object_detection: AI目标检测 (预留)

响应:
{
  "id": 1,
  "status": "pending",
  "message": "任务已提交"
}
```

### 3.2 获取任务列表
```
GET /tasks
Authorization: Bearer <token>

响应:
[
  {
    "id": 1,
    "pointcloud_id": 1,
    "scene_id": 1,
    "task_type": "voxel_grid_filter",
    "parameters": {"voxel_size": 0.05},
    "status": "success",
    "result_pointcloud_id": 2,
    "output_format": "ply",
    "error_message": null,
    "progress": 100,
    "created_by": 1,
    "created_at": "2024-01-01T00:00:00",
    "finished_at": "2024-01-01T00:01:00"
  }
]
```

## 4. 协同场景接口

### 4.1 创建协同场景
```
POST /scenes
Authorization: Bearer <token>

请求体:
{
  "name": "协同场景1",
  "description": "场景描述",
  "max_users": 10,
  "settings": {}
}

响应:
{
  "id": 1,
  "message": "场景创建成功"
}
```

### 4.2 获取场景列表
```
GET /scenes
Authorization: Bearer <token>

查询参数:
- include_inactive: boolean (默认false)

响应:
[
  {
    "id": 1,
    "name": "协同场景1",
    "description": "场景描述",
    "is_active": true,
    "max_users": 10,
    "created_by": 1,
    "created_by_name": "admin",
    "created_at": "2024-01-01T00:00:00",
    "pointcloud_count": 3,
    "active_users": 2
  }
]
```

### 4.3 获取场景详情
```
GET /scenes/{id}
Authorization: Bearer <token>

响应:
{
  "id": 1,
  "name": "协同场景1",
  "description": "场景描述",
  "is_active": true,
  "max_users": 10,
  "settings": {},
  "created_by": 1,
  "created_by_name": "admin",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "pointclouds": [
    {
      "id": 1,
      "scene_id": 1,
      "pointcloud_id": 1,
      "pointcloud_name": "点云1",
      "transform_matrix": null,
      "visible": true,
      "color": "#00d4ff",
      "opacity": 1.0,
      "order": 0,
      "added_by": 1,
      "added_by_name": "admin",
      "added_at": "2024-01-01T00:00:00"
    }
  ],
  "active_sessions": [
    {
      "id": 1,
      "user_id": 1,
      "username": "admin",
      "camera_position": {"x": 50, "y": 50, "z": 50},
      "camera_target": {"x": 0, "y": 0, "z": 0},
      "is_active": true,
      "joined_at": "2024-01-01T00:00:00"
    }
  ]
}
```

### 4.4 加入场景
```
POST /scenes/{id}/join
Authorization: Bearer <token>

响应:
{
  "session_token": "abc123...",
  "scene": { ... },  // 场景详情
  "message": "成功加入场景"
}
```

### 4.5 离开场景
```
POST /scenes/{id}/leave?session_token=<token>
Authorization: Bearer <token>

响应:
{
  "message": "已离开场景"
}
```

### 4.6 添加点云到场景
```
POST /scenes/{id}/pointclouds
Authorization: Bearer <token>

请求体:
{
  "pointcloud_id": 1,
  "transform_matrix": null,
  "visible": true,
  "color": "#00d4ff",
  "opacity": 1.0
}

响应:
{
  "id": 1,
  "message": "点云已添加到场景"
}
```

### 4.7 移除场景中的点云
```
DELETE /scenes/{scene_id}/pointclouds/{spc_id}
Authorization: Bearer <token>

响应:
{
  "message": "点云已从场景移除"
}
```

## 5. WebSocket 接口

### 5.1 连接
```
ws://host/api/v1/scenes/ws/{scene_id}?session_token=<token>
```

### 5.2 消息格式

#### 客户端发送

**相机更新**
```json
{
  "event_type": "camera_update",
  "camera_position": {"x": 50, "y": 50, "z": 50},
  "camera_target": {"x": 0, "y": 0, "z": 0}
}
```

**点云更新**
```json
{
  "event_type": "pointcloud_update",
  "data": {
    "pointcloud_id": 1,
    "visible": false
  }
}
```

**心跳**
```json
{
  "event_type": "ping"
}
```

#### 服务端推送

**用户加入**
```json
{
  "event_type": "user_joined",
  "scene_id": 1,
  "user_id": 2,
  "username": "engineer1",
  "timestamp": "2024-01-01T00:00:00"
}
```

**用户离开**
```json
{
  "event_type": "user_left",
  "scene_id": 1,
  "user_id": 2,
  "username": "engineer1",
  "timestamp": "2024-01-01T00:00:00"
}
```

**相机同步**
```json
{
  "event_type": "camera_update",
  "scene_id": 1,
  "user_id": 2,
  "username": "engineer1",
  "camera_position": {"x": 50, "y": 50, "z": 50},
  "camera_target": {"x": 0, "y": 0, "z": 0},
  "timestamp": "2024-01-01T00:00:00"
}
```

**任务进度**
```json
{
  "event_type": "task_progress",
  "scene_id": 1,
  "task_id": 1,
  "progress": 50,
  "status": "running",
  "message": "处理中...",
  "timestamp": "2024-01-01T00:00:00"
}
```

**任务完成**
```json
{
  "event_type": "task_completed",
  "scene_id": 1,
  "user_id": 1,
  "username": "admin",
  "data": {
    "task_id": 1,
    "result_pointcloud_id": 2
  },
  "timestamp": "2024-01-01T00:00:00"
}
```

## 6. 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

### 常见错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证或Token过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 413 | 文件过大 |
| 422 | 参数校验失败 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |
