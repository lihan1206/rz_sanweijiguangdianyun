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

export type TaskType = 'downsample' | 'denoise' | 'clip_z' | 'format_convert' | 
                        'voxel_grid' | 'statistical_outlier' | 'ransac_plane' | 
                        'passthrough' | 'icp_registration';
export type TaskStatus = 'pending' | 'running' | 'success' | 'failed';

// 协同会话类型
export interface CollaborativeSession {
  id: number;
  session_name: string;
  description: string | null;
  created_by: number;
  is_active: boolean;
  max_users: number;
  current_users: number;
  created_at: string;
  updated_at: string;
}

export interface SessionParticipant {
  id: number;
  session_id: number;
  user_id: number;
  joined_at: string;
  last_active: string;
  is_online: boolean;
}

export interface SessionUserInfo {
  user_id: number;
  username: string;
  role: string;
  is_online: boolean;
  joined_at: string;
}

export interface ProcessingTask {
  id: number;
  pointcloud_id: number;
  task_type: TaskType;
  parameters: Record<string, unknown> | null;
  status: TaskStatus;
  result_pointcloud_id: number | null;
  output_format: string;
  error_message: string | null;
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
