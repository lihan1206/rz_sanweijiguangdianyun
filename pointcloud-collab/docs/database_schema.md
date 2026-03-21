# 数据库表结构设计

## ER图

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    ER Diagram                                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     users       │       │  point_clouds   │       │  processing_    │
│                 │       │                 │       │    tasks        │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ PK id           │◄──────┤ FK user_id      │       │ PK id           │
│    username     │       │ PK id           │◄──────┤ FK point_cloud_ │
│    email        │       │    name         │       │    id           │
│    password_hash│       │    description  │       │ FK user_id      │
│    role         │       │    file_path    │       │    task_type    │
│    is_active    │       │    file_size    │       │    status       │
│    created_at   │       │    file_format  │       │    parameters   │
│    updated_at   │       │    point_count  │       │    result_path  │
└─────────────────┘       │    status       │       │    progress     │
                          │    visibility   │       │    started_at   │
                          │    scene_id     │◄─────┤    completed_at │
                          │    created_at   │       │    created_at   │
                          │    updated_at   │       │    updated_at   │
                          └─────────────────┘       └─────────────────┘
                                   │
                                   │
                                   ▼
                          ┌─────────────────┐
                          │     scenes      │
                          ├─────────────────┤
                          │ PK id           │
                          │    name         │
                          │    description  │
                          │    owner_id     │◄──────┐
                          │    visibility   │       │
                          │    created_at   │       │
                          │    updated_at   │       │
                          └─────────────────┘       │
                                   │                │
                                   │                │
                                   ▼                │
                          ┌─────────────────┐       │
                          │  scene_members  │       │
                          ├─────────────────┤       │
                          │ PK id           │       │
                          │ FK scene_id     │───────┘
                          │ FK user_id      │◄──────┘
                          │    role         │
                          │    joined_at    │
                          └─────────────────┘

┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  task_queues    │       │  file_chunks    │       │  ai_detections  │
│  (Future)       │       │                 │       │  (Future)       │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ PK id           │       │ PK id           │       │ PK id           │
│ FK task_id      │       │ FK point_cloud_ │       │ FK point_cloud_ │
│    worker_id    │       │    id           │       │    id           │
│    status       │       │    chunk_index  │       │    model_type   │
│    priority     │       │    chunk_size   │       │    detections   │
│    started_at   │       │    chunk_path   │       │    confidence   │
│    completed_at │       │    status       │       │    created_at   │
└─────────────────┘       │    created_at   │       └─────────────────┘
                          └─────────────────┘
```

## 表结构详细定义

### 1. users 表 - 用户表
```sql
CREATE TABLE users (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    email           VARCHAR(100) NOT NULL UNIQUE COMMENT '邮箱',
    password_hash   VARCHAR(255) NOT NULL COMMENT '密码哈希',
    full_name       VARCHAR(100) COMMENT '全名',
    avatar_url      VARCHAR(255) COMMENT '头像URL',
    role            ENUM('admin', 'user', 'guest') DEFAULT 'user' COMMENT '角色',
    is_active       BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    last_login      TIMESTAMP NULL COMMENT '最后登录时间',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_email (email),
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
```

### 2. scenes 表 - 场景表（协同工作空间）
```sql
CREATE TABLE scenes (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL COMMENT '场景名称',
    description     TEXT COMMENT '场景描述',
    owner_id        BIGINT UNSIGNED NOT NULL COMMENT '创建者ID',
    visibility      ENUM('private', 'public', 'shared') DEFAULT 'private' COMMENT '可见性',
    max_members     INT DEFAULT 10 COMMENT '最大成员数',
    settings        JSON COMMENT '场景设置',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_owner (owner_id),
    INDEX idx_visibility (visibility)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景表';
```

### 3. scene_members 表 - 场景成员表
```sql
CREATE TABLE scene_members (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    scene_id        BIGINT UNSIGNED NOT NULL COMMENT '场景ID',
    user_id         BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    role            ENUM('owner', 'editor', 'viewer') DEFAULT 'viewer' COMMENT '角色',
    permissions     JSON COMMENT '权限配置',
    joined_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active     TIMESTAMP NULL COMMENT '最后活跃时间',
    
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uk_scene_user (scene_id, user_id),
    INDEX idx_scene (scene_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景成员表';
```

### 4. point_clouds 表 - 点云数据表
```sql
CREATE TABLE point_clouds (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id             BIGINT UNSIGNED NOT NULL COMMENT '上传用户ID',
    scene_id            BIGINT UNSIGNED COMMENT '所属场景ID',
    name                VARCHAR(200) NOT NULL COMMENT '点云名称',
    description         TEXT COMMENT '描述',
    original_filename   VARCHAR(255) NOT NULL COMMENT '原始文件名',
    file_path           VARCHAR(500) NOT NULL COMMENT '存储路径',
    file_size           BIGINT UNSIGNED NOT NULL COMMENT '文件大小(字节)',
    file_format         ENUM('ply', 'las', 'laz', 'xyz', 'pcd', 'obj') NOT NULL COMMENT '文件格式',
    file_hash           VARCHAR(64) COMMENT '文件MD5哈希',
    point_count         BIGINT UNSIGNED COMMENT '点数',
    bounding_box        JSON COMMENT '包围盒 {min: [x,y,z], max: [x,y,z]}',
    has_color           BOOLEAN DEFAULT FALSE COMMENT '是否包含颜色',
    has_normal          BOOLEAN DEFAULT FALSE COMMENT '是否包含法线',
    coordinate_system   VARCHAR(50) COMMENT '坐标系',
    status              ENUM('uploading', 'processing', 'ready', 'error', 'deleted') DEFAULT 'uploading' COMMENT '状态',
    visibility          ENUM('private', 'public', 'scene_only') DEFAULT 'private' COMMENT '可见性',
    version             INT DEFAULT 1 COMMENT '版本号',
    parent_id           BIGINT UNSIGNED COMMENT '父点云ID（用于版本管理）',
    metadata            JSON COMMENT '元数据',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_id) REFERENCES point_clouds(id) ON DELETE SET NULL,
    INDEX idx_user (user_id),
    INDEX idx_scene (scene_id),
    INDEX idx_status (status),
    INDEX idx_visibility (visibility),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='点云数据表';
```

### 5. processing_tasks 表 - 处理任务表
```sql
CREATE TABLE processing_tasks (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    point_cloud_id      BIGINT UNSIGNED NOT NULL COMMENT '处理的点云ID',
    user_id             BIGINT UNSIGNED NOT NULL COMMENT '创建任务的用户ID',
    scene_id            BIGINT UNSIGNED COMMENT '所属场景ID',
    task_type           ENUM('filter_voxel', 'filter_statistical', 'segment_ransac', 'register_icp', 'convert_format', 'ai_detection') NOT NULL COMMENT '任务类型',
    task_name           VARCHAR(200) COMMENT '任务名称',
    status              ENUM('pending', 'queued', 'running', 'completed', 'failed', 'cancelled') DEFAULT 'pending' COMMENT '状态',
    priority            INT DEFAULT 5 COMMENT '优先级(1-10, 数字越小优先级越高)',
    parameters          JSON NOT NULL COMMENT '处理参数',
    result_point_cloud_id BIGINT UNSIGNED COMMENT '结果点云ID',
    result_summary      JSON COMMENT '结果摘要',
    error_message       TEXT COMMENT '错误信息',
    progress            FLOAT DEFAULT 0 COMMENT '进度(0-100)',
    worker_id           VARCHAR(100) COMMENT '执行worker ID',
    started_at          TIMESTAMP NULL COMMENT '开始时间',
    completed_at        TIMESTAMP NULL COMMENT '完成时间',
    estimated_duration  INT COMMENT '预估耗时(秒)',
    actual_duration     INT COMMENT '实际耗时(秒)',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (point_cloud_id) REFERENCES point_clouds(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL,
    FOREIGN KEY (result_point_cloud_id) REFERENCES point_clouds(id) ON DELETE SET NULL,
    INDEX idx_point_cloud (point_cloud_id),
    INDEX idx_user (user_id),
    INDEX idx_scene (scene_id),
    INDEX idx_status (status),
    INDEX idx_type_status (task_type, status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='处理任务表';
```

### 6. file_chunks 表 - 文件分片表（大文件上传支持）
```sql
CREATE TABLE file_chunks (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    upload_id           VARCHAR(64) NOT NULL COMMENT '上传会话ID',
    point_cloud_id      BIGINT UNSIGNED COMMENT '关联的点云ID（上传完成后设置）',
    user_id             BIGINT UNSIGNED NOT NULL COMMENT '上传用户ID',
    file_name           VARCHAR(255) NOT NULL COMMENT '文件名',
    file_size           BIGINT UNSIGNED NOT NULL COMMENT '文件总大小',
    chunk_index         INT NOT NULL COMMENT '分片序号',
    chunk_size          INT NOT NULL COMMENT '分片大小',
    chunk_path          VARCHAR(500) COMMENT '分片存储路径',
    chunk_hash          VARCHAR(64) COMMENT '分片MD5',
    total_chunks        INT NOT NULL COMMENT '总分片数',
    status              ENUM('pending', 'uploaded', 'merged', 'failed') DEFAULT 'pending' COMMENT '状态',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (point_cloud_id) REFERENCES point_clouds(id) ON DELETE SET NULL,
    UNIQUE KEY uk_upload_chunk (upload_id, chunk_index),
    INDEX idx_upload (upload_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文件分片表';
```

### 7. ai_detections 表 - AI检测结果表（预留）
```sql
CREATE TABLE ai_detections (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    point_cloud_id      BIGINT UNSIGNED NOT NULL COMMENT '点云ID',
    task_id             BIGINT UNSIGNED COMMENT '关联任务ID',
    model_type          VARCHAR(50) NOT NULL COMMENT '模型类型',
    model_version       VARCHAR(20) COMMENT '模型版本',
    detections          JSON NOT NULL COMMENT '检测结果 [{class, confidence, bbox, points}]',
    statistics          JSON COMMENT '统计信息',
    processing_time     FLOAT COMMENT '处理时间(秒)',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (point_cloud_id) REFERENCES point_clouds(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES processing_tasks(id) ON DELETE SET NULL,
    INDEX idx_point_cloud (point_cloud_id),
    INDEX idx_model (model_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI检测结果表';
```

### 8. activity_logs 表 - 活动日志表
```sql
CREATE TABLE activity_logs (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id             BIGINT UNSIGNED COMMENT '用户ID',
    scene_id            BIGINT UNSIGNED COMMENT '场景ID',
    action_type         VARCHAR(50) NOT NULL COMMENT '操作类型',
    target_type         VARCHAR(50) COMMENT '目标类型 (point_cloud, task, scene)',
    target_id           BIGINT UNSIGNED COMMENT '目标ID',
    details             JSON COMMENT '详细信息',
    ip_address          VARCHAR(45) COMMENT 'IP地址',
    user_agent          VARCHAR(500) COMMENT '用户代理',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL,
    INDEX idx_user (user_id),
    INDEX idx_scene (scene_id),
    INDEX idx_action (action_type),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='活动日志表';
```

## 数据库关系说明

### 关系图
```
users ||--o{ point_clouds : uploads
users ||--o{ scenes : owns
users ||--o{ scene_members : participates
users ||--o{ processing_tasks : creates
users ||--o{ file_chunks : uploads

scenes ||--o{ scene_members : has
scenes ||--o{ point_clouds : contains
scenes ||--o{ processing_tasks : has

point_clouds ||--o{ processing_tasks : processed_as
point_clouds ||--o{ processing_tasks : results_in
point_clouds ||--o{ file_chunks : uploaded_via
point_clouds ||--o{ ai_detections : detected_in
point_clouds ||--o{ point_clouds : versions

processing_tasks ||--o{ ai_detections : generates
```

## 索引策略

### 高频查询场景索引
1. **用户点云列表**: `(user_id, status, created_at)`
2. **场景点云列表**: `(scene_id, status, created_at)`
3. **任务队列**: `(status, priority, created_at)`
4. **用户任务**: `(user_id, status, created_at)`
5. **文件分片查询**: `(upload_id, chunk_index)`

### 全文搜索支持
```sql
-- 点云名称和描述全文索引
ALTER TABLE point_clouds ADD FULLTEXT INDEX ft_name_desc (name, description);

-- 场景名称和描述全文索引
ALTER TABLE scenes ADD FULLTEXT INDEX ft_name_desc (name, description);
```

## 分区策略（大数据量场景）

### point_clouds 表分区
```sql
-- 按创建时间范围分区
ALTER TABLE point_clouds 
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION pfuture VALUES LESS THAN MAXVALUE
);
```

### processing_tasks 表分区
```sql
-- 按状态分区（LIST分区）
ALTER TABLE processing_tasks
PARTITION BY LIST COLUMNS(status) (
    PARTITION p_pending VALUES IN ('pending', 'queued'),
    PARTITION p_running VALUES IN ('running'),
    PARTITION p_completed VALUES IN ('completed', 'failed', 'cancelled')
);
```

## 数据保留策略

### 自动清理任务
```sql
-- 清理已删除的点云数据（软删除后30天）
-- 清理已完成任务（完成后90天）
-- 清理活动日志（180天）
-- 清理失败的分片（7天）
```
