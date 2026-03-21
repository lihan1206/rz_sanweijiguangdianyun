export type UserRole = 'admin' | 'engineer' | 'viewer';

export interface User {
  id: number;
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface PointCloud {
  id: number;
  name: string;
  original_filename: string;
  file_format: string;
  file_size: number;
  points_count: number | null;
  group_name: string | null;
  tags: string[] | null;
  version: number;
  is_archived: boolean;
  is_deleted: boolean;
  capture_time: string | null;
  created_at: string;
}

export interface PointCloudStats {
  total_points: number;
  density_estimate: number;
  x_range: [number, number];
  y_range: [number, number];
  z_range: [number, number];
}

export interface PointSample {
  points: number[][];
}

export type TaskType = 
  | 'downsample' 
  | 'denoise' 
  | 'clip_z' 
  | 'format_convert'
  | 'voxel_grid_filter'
  | 'statistical_outlier_removal'
  | 'ransac_plane_segmentation'
  | 'icp_registration'
  | 'ai_object_detection';

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed';

export interface ProcessingTask {
  id: number;
  pointcloud_id: number;
  scene_id: number | null;
  task_type: TaskType;
  parameters: Record<string, unknown> | null;
  status: TaskStatus;
  result_pointcloud_id: number | null;
  output_format: string;
  error_message: string | null;
  progress: number;
  created_by: number;
  created_at: string;
  finished_at: string | null;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  action: string;
  target_type: string;
  target_id: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface ScenePointCloud {
  id: number;
  scene_id: number;
  pointcloud_id: number;
  pointcloud_name: string;
  transform_matrix: Record<string, unknown> | null;
  visible: boolean;
  color: string | null;
  opacity: number;
  order: number;
  added_by: number;
  added_by_name: string;
  added_at: string;
}

export interface SessionInfo {
  id: number;
  user_id: number;
  username: string;
  camera_position: Record<string, number> | null;
  camera_target: Record<string, number> | null;
  is_active: boolean;
  joined_at: string;
}

export interface CollaborationScene {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  max_users: number;
  settings: Record<string, unknown> | null;
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  pointclouds: ScenePointCloud[];
  active_sessions: SessionInfo[];
}

export interface SceneListItem {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  max_users: number;
  created_by: number;
  created_by_name: string;
  created_at: string;
  pointcloud_count: number;
  active_users: number;
}

export interface WebSocketMessage {
  event_type: string;
  scene_id: number;
  user_id: number;
  username: string;
  data?: Record<string, unknown>;
  timestamp: string;
  camera_position?: Record<string, number>;
  camera_target?: Record<string, number>;
  task_id?: number;
  progress?: number;
  status?: string;
  message?: string;
}
