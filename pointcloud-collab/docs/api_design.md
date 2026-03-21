# API接口设计文档

## 基础信息

- **Base URL**: `/api/v1`
- **认证方式**: JWT Bearer Token
- **数据格式**: JSON
- **字符编码**: UTF-8

## 认证相关接口

### 1. 用户注册
```http
POST /auth/register
Content-Type: application/json

Request:
{
    "username": "string",       // 必填，3-50字符
    "email": "string",          // 必填，有效邮箱
    "password": "string",       // 必填，8-128字符，需包含字母和数字
    "full_name": "string"       // 可选
}

Response 201:
{
    "code": 201,
    "message": "User registered successfully",
    "data": {
        "id": 1,
        "username": "john_doe",
        "email": "john@example.com",
        "full_name": "John Doe",
        "created_at": "2024-01-15T10:30:00Z"
    }
}

Response 400:
{
    "code": 400,
    "message": "Validation error",
    "errors": {
        "email": ["Email already exists"]
    }
}
```

### 2. 用户登录
```http
POST /auth/login
Content-Type: application/json

Request:
{
    "username": "string",       // 用户名或邮箱
    "password": "string"
}

Response 200:
{
    "code": 200,
    "message": "Login successful",
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "Bearer",
        "expires_in": 3600,
        "user": {
            "id": 1,
            "username": "john_doe",
            "email": "john@example.com",
            "role": "user"
        }
    }
}

Response 401:
{
    "code": 401,
    "message": "Invalid credentials"
}
```

### 3. 刷新Token
```http
POST /auth/refresh
Authorization: Bearer {refresh_token}

Response 200:
{
    "code": 200,
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "Bearer",
        "expires_in": 3600
    }
}
```

### 4. 登出
```http
POST /auth/logout
Authorization: Bearer {access_token}

Response 200:
{
    "code": 200,
    "message": "Logout successful"
}
```

## 点云文件接口

### 5. 上传点云文件（支持分片上传）
```http
POST /pointclouds/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

Request (普通上传):
{
    "file": File,               // 点云文件 (.ply, .las, .laz, .xyz, .pcd)
    "name": "string",           // 点云名称
    "description": "string",    // 描述
    "scene_id": 1,              // 可选，关联场景
    "visibility": "private"     // private/public/scene_only
}

Request (初始化分片上传):
POST /pointclouds/upload/init
{
    "file_name": "large_file.ply",
    "file_size": 52428800,      // 50MB
    "chunk_size": 5242880,      // 5MB每片
    "name": "Large Point Cloud",
    "description": "..."
}

Response (初始化):
{
    "code": 200,
    "data": {
        "upload_id": "uuid-string",
        "total_chunks": 10,
        "chunk_size": 5242880
    }
}

Request (上传分片):
POST /pointclouds/upload/chunk
Content-Type: multipart/form-data
{
    "upload_id": "uuid-string",
    "chunk_index": 0,
    "chunk": File
}

Request (合并分片):
POST /pointclouds/upload/merge
{
    "upload_id": "uuid-string"
}

Response 201:
{
    "code": 201,
    "message": "Point cloud uploaded successfully",
    "data": {
        "id": 1,
        "name": "My Point Cloud",
        "file_format": "ply",
        "file_size": 52428800,
        "point_count": 10000000,
        "status": "processing",
        "created_at": "2024-01-15T10:30:00Z"
    }
}

Response 413:
{
    "code": 413,
    "message": "File too large. Maximum size is 500MB"
}

Response 415:
{
    "code": 415,
    "message": "Unsupported file format. Supported: .ply, .las, .laz, .xyz, .pcd"
}
```

### 6. 获取点云列表
```http
GET /pointclouds
Authorization: Bearer {token}

Query Parameters:
- page: int (default: 1)
- page_size: int (default: 20, max: 100)
- status: string (uploading/processing/ready/error)
- scene_id: int
- search: string (搜索名称和描述)
- sort_by: string (created_at/updated_at/name/point_count)
- sort_order: string (asc/desc)

Response 200:
{
    "code": 200,
    "data": {
        "items": [
            {
                "id": 1,
                "name": "My Point Cloud",
                "description": "...",
                "file_format": "ply",
                "file_size": 52428800,
                "point_count": 10000000,
                "status": "ready",
                "visibility": "private",
                "has_color": true,
                "has_normal": false,
                "bounding_box": {
                    "min": [-10.5, -5.2, 0.0],
                    "max": [10.5, 5.2, 8.3]
                },
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:35:00Z",
                "owner": {
                    "id": 1,
                    "username": "john_doe"
                }
            }
        ],
        "total": 100,
        "page": 1,
        "page_size": 20,
        "pages": 5
    }
}
```

### 7. 获取点云详情
```http
GET /pointclouds/{id}
Authorization: Bearer {token}

Response 200:
{
    "code": 200,
    "data": {
        "id": 1,
        "name": "My Point Cloud",
        "description": "...",
        "file_format": "ply",
        "file_size": 52428800,
        "point_count": 10000000,
        "status": "ready",
        "visibility": "private",
        "has_color": true,
        "has_normal": false,
        "bounding_box": {...},
        "coordinate_system": "EPSG:4326",
        "metadata": {...},
        "scene_id": 1,
        "version": 1,
        "created_at": "...",
        "updated_at": "...",
        "owner": {...},
        "processing_tasks": [...],
        "download_url": "/api/v1/pointclouds/1/download"
    }
}
```

### 8. 获取点云数据（用于可视化）
```http
GET /pointclouds/{id}/data
Authorization: Bearer {token}

Query Parameters:
- format: string (json/bin) - 返回格式，默认json
- max_points: int (default: 1000000) - 最大返回点数（用于LOD）
- downsample: float - 下采样比例

Response 200 (JSON格式):
{
    "code": 200,
    "data": {
        "format": "json",
        "point_count": 1000000,
        "has_color": true,
        "has_normal": false,
        "bounding_box": {...},
        "points_url": "/api/v1/pointclouds/1/points.bin",
        "colors_url": "/api/v1/pointclouds/1/colors.bin",
        "preview_image": "/api/v1/pointclouds/1/preview.png"
    }
}

Response 200 (二进制流):
Content-Type: application/octet-stream
[二进制点云数据]
```

### 9. 更新点云信息
```http
PUT /pointclouds/{id}
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
    "name": "New Name",
    "description": "New description",
    "visibility": "public"
}

Response 200:
{
    "code": 200,
    "message": "Point cloud updated",
    "data": {...}
}
```

### 10. 删除点云
```http
DELETE /pointclouds/{id}
Authorization: Bearer {token}

Response 200:
{
    "code": 200,
    "message": "Point cloud deleted"
}
```

### 11. 导出点云
```http
POST /pointclouds/{id}/export
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
    "format": "obj",            // ply/obj/xyz
    "include_color": true,
    "include_normal": false,
    "transform": {              // 可选变换
        "scale": [1, 1, 1],
        "rotation": [0, 0, 0],
        "translation": [0, 0, 0]
    }
}

Response 202:
{
    "code": 202,
    "message": "Export task created",
    "data": {
        "task_id": 123,
        "status": "queued",
        "download_url": null
    }
}
```

## 处理任务接口

### 12. 创建处理任务
```http
POST /tasks
Authorization: Bearer {token}
Content-Type: application/json

Request (Voxel Grid滤波):
{
    "point_cloud_id": 1,
    "task_type": "filter_voxel",
    "task_name": "Voxel Downsample",
    "parameters": {
        "voxel_size": 0.05       // 体素大小
    },
    "scene_id": 1               // 可选，用于实时同步
}

Request (统计滤波):
{
    "point_cloud_id": 1,
    "task_type": "filter_statistical",
    "task_name": "Statistical Outlier Removal",
    "parameters": {
        "nb_neighbors": 20,      // 邻域点数
        "std_ratio": 2.0         // 标准差倍数
    }
}

Request (RANSAC平面分割):
{
    "point_cloud_id": 1,
    "task_type": "segment_ransac",
    "task_name": "Plane Segmentation",
    "parameters": {
        "distance_threshold": 0.01,    // 距离阈值
        "ransac_n": 3,                 // 采样点数
        "num_iterations": 1000         // 迭代次数
    }
}

Request (ICP配准):
{
    "point_cloud_id": 1,
    "task_type": "register_icp",
    "task_name": "ICP Registration",
    "parameters": {
        "target_point_cloud_id": 2,    // 目标点云ID
        "max_correspondence_distance": 0.05,
        "init_transform": [...],       // 初始变换矩阵(可选)
        "max_iterations": 30
    }
}

Response 201:
{
    "code": 201,
    "message": "Task created",
    "data": {
        "id": 123,
        "task_type": "filter_voxel",
        "status": "pending",
        "priority": 5,
        "progress": 0,
        "estimated_duration": 60,
        "created_at": "2024-01-15T10:30:00Z"
    }
}
```

### 13. 获取任务列表
```http
GET /tasks
Authorization: Bearer {token}

Query Parameters:
- page: int
- page_size: int
- status: string
- point_cloud_id: int
- scene_id: int

Response 200:
{
    "code": 200,
    "data": {
        "items": [
            {
                "id": 123,
                "task_type": "filter_voxel",
                "task_name": "Voxel Downsample",
                "status": "completed",
                "progress": 100,
                "point_cloud_id": 1,
                "result_point_cloud_id": 2,
                "started_at": "...",
                "completed_at": "...",
                "actual_duration": 45
            }
        ],
        "total": 50
    }
}
```

### 14. 获取任务详情
```http
GET /tasks/{id}
Authorization: Bearer {token}

Response 200:
{
    "code": 200,
    "data": {
        "id": 123,
        "task_type": "filter_voxel",
        "task_name": "Voxel Downsample",
        "status": "completed",
        "parameters": {...},
        "result_summary": {
            "input_points": 10000000,
            "output_points": 500000,
            "processing_time": 45.2
        },
        "progress": 100,
        "error_message": null,
        "point_cloud": {...},
        "result_point_cloud": {...},
        "created_at": "...",
        "started_at": "...",
        "completed_at": "..."
    }
}
```

### 15. 取消任务
```http
POST /tasks/{id}/cancel
Authorization: Bearer {token}

Response 200:
{
    "code": 200,
    "message": "Task cancelled"
}
```

## 场景协同接口

### 16. 创建场景
```http
POST /scenes
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
    "name": "Collaboration Scene",
    "description": "Team workspace",
    "visibility": "shared",
    "max_members": 10
}

Response 201:
{
    "code": 201,
    "data": {
        "id": 1,
        "name": "Collaboration Scene",
        "owner_id": 1,
        "invite_code": "ABC123XYZ",
        "created_at": "..."
    }
}
```

### 17. 获取场景列表
```http
GET /scenes
Authorization: Bearer {token}

Query Parameters:
- owned: bool (只显示我创建的)
- joined: bool (只显示我加入的)

Response 200:
{
    "code": 200,
    "data": {
        "items": [
            {
                "id": 1,
                "name": "Collaboration Scene",
                "description": "...",
                "owner": {...},
                "member_count": 5,
                "point_cloud_count": 3,
                "visibility": "shared",
                "created_at": "..."
            }
        ]
    }
}
```

### 18. 加入场景
```http
POST /scenes/{id}/join
Authorization: Bearer {token}
Content-Type: application/json

Request:
{
    "invite_code": "ABC123XYZ"  // 或通过邀请链接
}

Response 200:
{
    "code": 200,
    "message": "Joined scene successfully"
}
```

### 19. 获取场景成员
```http
GET /scenes/{id}/members
Authorization: Bearer {token}

Response 200:
{
    "code": 200,
    "data": {
        "members": [
            {
                "id": 1,
                "user": {...},
                "role": "owner",
                "joined_at": "...",
                "last_active": "..."
            }
        ]
    }
}
```

### 20. 获取场景点云（协同视图）
```http
GET /scenes/{id}/pointclouds
Authorization: Bearer {token}

Response 200:
{
    "code": 200,
    "data": {
        "scene_id": 1,
        "point_clouds": [
            {
                "id": 1,
                "name": "User A's Point Cloud",
                "owner": {...},
                "status": "ready",
                "transform": {          // 场景中的变换
                    "position": [0, 0, 0],
                    "rotation": [0, 0, 0],
                    "scale": [1, 1, 1]
                },
                "visible": true,
                "color": "#FF0000"     // 显示颜色
            }
        ],
        "active_users": [           // 当前在线用户
            {
                "id": 1,
                "username": "john_doe",
                "cursor_position": [1.5, 2.0, 0.5],
                "view_matrix": [...]
            }
        ]
    }
}
```

## WebSocket实时通信

### 连接
```javascript
const socket = io('/api/v1/ws', {
    auth: {
        token: 'Bearer {access_token}'
    }
});
```

### 事件定义

#### 客户端发送事件
```javascript
// 加入场景
socket.emit('scene:join', { scene_id: 1 });

// 离开场景
socket.emit('scene:leave', { scene_id: 1 });

// 更新视角
socket.emit('user:view_update', {
    scene_id: 1,
    view_matrix: [...],
    cursor_position: [x, y, z]
});

// 更新点云变换
socket.emit('pointcloud:transform', {
    scene_id: 1,
    point_cloud_id: 1,
    transform: {
        position: [x, y, z],
        rotation: [rx, ry, rz],
        scale: [sx, sy, sz]
    }
});

// 切换点云可见性
socket.emit('pointcloud:visibility', {
    scene_id: 1,
    point_cloud_id: 1,
    visible: false
});
```

#### 服务端推送事件
```javascript
// 用户加入
socket.on('user:joined', (data) => {
    // { user_id, username, joined_at }
});

// 用户离开
socket.on('user:left', (data) => {
    // { user_id, username }
});

// 用户视角更新
socket.on('user:view_updated', (data) => {
    // { user_id, view_matrix, cursor_position }
});

// 点云上传完成
socket.on('pointcloud:uploaded', (data) => {
    // { point_cloud_id, name, owner, scene_id }
});

// 点云处理状态更新
socket.on('pointcloud:processing', (data) => {
    // { point_cloud_id, task_id, status, progress }
});

// 点云处理完成
socket.on('pointcloud:completed', (data) => {
    // { point_cloud_id, task_id, result_point_cloud_id }
});

// 点云变换更新
socket.on('pointcloud:transform_updated', (data) => {
    // { point_cloud_id, transform, updated_by }
});

// 点云可见性更新
socket.on('pointcloud:visibility_updated', (data) => {
    // { point_cloud_id, visible, updated_by }
});

// 任务创建
socket.on('task:created', (data) => {
    // { task_id, task_type, point_cloud_id, created_by }
});

// 任务进度
socket.on('task:progress', (data) => {
    // { task_id, progress, status }
});

// 任务完成
socket.on('task:completed', (data) => {
    // { task_id, result_point_cloud_id, completed_by }
});

// 错误通知
socket.on('error', (data) => {
    // { code, message }
});
```

## 错误处理

### 错误响应格式
```json
{
    "code": 400,
    "message": "Error description",
    "error_code": "VALIDATION_ERROR",
    "details": {},
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req-uuid-string"
}
```

### 错误码定义
| HTTP Code | Error Code | Description |
|-----------|------------|-------------|
| 400 | VALIDATION_ERROR | 请求参数验证失败 |
| 400 | BAD_REQUEST | 错误的请求 |
| 401 | UNAUTHORIZED | 未认证 |
| 401 | TOKEN_EXPIRED | Token已过期 |
| 403 | FORBIDDEN | 无权限访问 |
| 404 | NOT_FOUND | 资源不存在 |
| 409 | CONFLICT | 资源冲突 |
| 413 | PAYLOAD_TOO_LARGE | 请求体过大 |
| 415 | UNSUPPORTED_MEDIA_TYPE | 不支持的媒体类型 |
| 422 | UNPROCESSABLE_ENTITY | 无法处理的实体 |
| 429 | TOO_MANY_REQUESTS | 请求过于频繁 |
| 500 | INTERNAL_ERROR | 服务器内部错误 |
| 502 | BAD_GATEWAY | 网关错误 |
| 503 | SERVICE_UNAVAILABLE | 服务不可用 |
| 504 | GATEWAY_TIMEOUT | 网关超时 |

### 文件上传错误处理
```json
{
    "code": 413,
    "message": "File upload failed",
    "error_code": "FILE_TOO_LARGE",
    "details": {
        "max_size": 524288000,
        "actual_size": 629145600,
        "unit": "bytes"
    }
}
```

### 处理超时错误
```json
{
    "code": 504,
    "message": "Processing timeout",
    "error_code": "PROCESSING_TIMEOUT",
    "details": {
        "task_id": 123,
        "timeout_seconds": 300,
        "partial_result_available": true
    }
}
```

## 限流策略

### API限流
- 认证接口: 5次/分钟
- 文件上传: 10次/分钟
- 任务创建: 20次/分钟
- 其他接口: 100次/分钟

### 响应头
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642245600
```

### 限流响应
```http
429 Too Many Requests
Retry-After: 60

{
    "code": 429,
    "message": "Rate limit exceeded",
    "error_code": "TOO_MANY_REQUESTS",
    "retry_after": 60
}
```
