-- 三维激光点云处理平台数据库表结构
-- 支持多用户协同处理、任务队列、版本控制

USE pointcloud_platform;

-- 用户表 (已存在，保留现有结构)
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'engineer', 'viewer') NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 协同会话表 - 支持多用户协同处理同一场景
CREATE TABLE IF NOT EXISTS collaborative_sessions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    session_name VARCHAR(128) NOT NULL,
    description TEXT,
    created_by INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    max_users INT NOT NULL DEFAULT 10,
    current_users INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_created_by (created_by),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 会话参与者表 - 记录哪些用户在哪个会话中
CREATE TABLE IF NOT EXISTS session_participants (
    id INT PRIMARY KEY AUTO_INCREMENT,
    session_id INT NOT NULL,
    user_id INT NOT NULL,
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_online BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE KEY uk_session_user (session_id, user_id),
    FOREIGN KEY (session_id) REFERENCES collaborative_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_online (is_online)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 点云数据表 (已存在，扩展版本控制字段)
CREATE TABLE IF NOT EXISTS pointclouds (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(255) NOT NULL,
    file_format VARCHAR(16) NOT NULL,
    file_size INT NOT NULL,
    points_count INT,
    capture_time DATETIME,
    sensor_model VARCHAR(128),
    coordinate_system VARCHAR(128),
    bounding_box JSON,
    group_name VARCHAR(64),
    tags JSON,
    version INT NOT NULL DEFAULT 1,
    parent_id INT, -- 父版本ID，用于版本追溯
    session_id INT, -- 所属协同会话
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at DATETIME,
    created_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES pointclouds(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES collaborative_sessions(id) ON DELETE SET NULL,
    INDEX idx_name (name),
    INDEX idx_group (group_name),
    INDEX idx_created_by (created_by),
    INDEX idx_session_id (session_id),
    INDEX idx_deleted (is_deleted),
    INDEX idx_version (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 任务队列 (已存在，扩展处理类型和参数)
CREATE TABLE IF NOT EXISTS processing_tasks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pointcloud_id INT NOT NULL,
    session_id INT, -- 所属协同会话
    task_type ENUM('downsample', 'denoise', 'clip_z', 'format_convert', 
                   'voxel_grid', 'statistical_outlier', 'ransac_plane', 'icp_registration') NOT NULL,
    parameters JSON,
    status ENUM('pending', 'running', 'success', 'failed') NOT NULL DEFAULT 'pending',
    result_pointcloud_id INT,
    output_format VARCHAR(16) NOT NULL DEFAULT 'xyz',
    error_message TEXT,
    priority INT NOT NULL DEFAULT 5, -- 任务优先级 1-10
    created_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    finished_at DATETIME,
    FOREIGN KEY (pointcloud_id) REFERENCES pointclouds(id) ON DELETE CASCADE,
    FOREIGN KEY (result_pointcloud_id) REFERENCES pointclouds(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES collaborative_sessions(id) ON DELETE SET NULL,
    INDEX idx_status (status),
    INDEX idx_pointcloud_id (pointcloud_id),
    INDEX idx_created_by (created_by),
    INDEX idx_session_id (session_id),
    INDEX idx_priority (priority),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 审计日志表 (已存在)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    action VARCHAR(128) NOT NULL,
    target_type VARCHAR(64),
    target_id VARCHAR(64),
    detail JSON,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 导出任务表 - 记录导出请求
CREATE TABLE IF NOT EXISTS export_tasks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pointcloud_id INT NOT NULL,
    user_id INT NOT NULL,
    export_format ENUM('ply', 'obj', 'xyz', 'las') NOT NULL DEFAULT 'ply',
    status ENUM('pending', 'processing', 'completed', 'failed') NOT NULL DEFAULT 'pending',
    storage_path VARCHAR(255),
    file_size INT,
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    FOREIGN KEY (pointcloud_id) REFERENCES pointclouds(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(128) NOT NULL UNIQUE,
    config_value TEXT,
    description TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 初始化默认配置
INSERT IGNORE INTO system_configs (config_key, config_value, description) VALUES
('max_file_size_mb', '500', '最大上传文件大小(MB)'),
('allowed_formats', 'las,laz,ply,xyz,e57,csv', '允许的点云格式'),
('task_concurrent_limit', '4', '并发处理任务数'),
('session_timeout_minutes', '30', '会话超时时间(分钟)'),
('cleanup_days', '30', '回收站清理天数');
