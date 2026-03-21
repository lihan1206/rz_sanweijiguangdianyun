CREATE DATABASE IF NOT EXISTS pointcloud_platform DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE pointcloud_platform;

CREATE TABLE IF NOT EXISTS collaboration_scenes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    max_users INT DEFAULT 10 NOT NULL,
    settings JSON,
    created_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scene_pointclouds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scene_id INT NOT NULL,
    pointcloud_id INT NOT NULL,
    transform_matrix JSON,
    visible BOOLEAN DEFAULT TRUE NOT NULL,
    color VARCHAR(32),
    opacity DOUBLE DEFAULT 1.0 NOT NULL,
    `order` INT DEFAULT 0 NOT NULL,
    added_by INT NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (scene_id) REFERENCES collaboration_scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (pointcloud_id) REFERENCES pointclouds(id) ON DELETE CASCADE,
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_scene_pointcloud (scene_id, pointcloud_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS collaboration_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scene_id INT NOT NULL,
    user_id INT NOT NULL,
    session_token VARCHAR(64) UNIQUE NOT NULL,
    camera_position JSON,
    camera_target JSON,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    left_at DATETIME,
    FOREIGN KEY (scene_id) REFERENCES collaboration_scenes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_token (session_token),
    INDEX idx_active_sessions (scene_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE processing_tasks 
ADD COLUMN scene_id INT NULL,
ADD COLUMN progress INT DEFAULT 0 NOT NULL,
ADD CONSTRAINT fk_task_scene FOREIGN KEY (scene_id) REFERENCES collaboration_scenes(id) ON DELETE SET NULL;
