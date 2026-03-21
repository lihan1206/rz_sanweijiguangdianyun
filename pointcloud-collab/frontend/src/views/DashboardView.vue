<template>
  <div class="dashboard-view">
    <el-row :gutter="20">
      <!-- 统计卡片 -->
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon" style="background: #409eff;">
            <el-icon :size="32"><DataAnalysis /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.pointCloudCount }}</div>
            <div class="stat-label">点云文件</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon" style="background: #67c23a;">
            <el-icon :size="32"><UserFilled /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.sceneCount }}</div>
            <div class="stat-label">协同场景</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon" style="background: #e6a23c;">
            <el-icon :size="32"><List /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.taskCount }}</div>
            <div class="stat-label">处理任务</div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-icon" style="background: #f56c6c;">
            <el-icon :size="32"><TrendCharts /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ formatSize(stats.totalSize) }}</div>
            <div class="stat-label">存储使用</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" class="mt-20">
      <!-- 最近点云 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近上传的点云</span>
              <el-button type="primary" link @click="$router.push('/pointclouds')">
                查看全部
              </el-button>
            </div>
          </template>
          
          <el-table :data="recentPointClouds" v-loading="loading">
            <el-table-column prop="name" label="名称" show-overflow-tooltip />
            <el-table-column prop="file_format" label="格式" width="80" />
            <el-table-column prop="point_count" label="点数" width="120">
              <template #default="{ row }">
                {{ formatNumber(row.point_count) }}
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="上传时间" width="160">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      
      <!-- 最近任务 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近处理任务</span>
              <el-button type="primary" link @click="$router.push('/tasks')">
                查看全部
              </el-button>
            </div>
          </template>
          
          <el-table :data="recentTasks" v-loading="loading">
            <el-table-column prop="task_name" label="任务名称" show-overflow-tooltip />
            <el-table-column prop="task_type" label="类型" width="120">
              <template #default="{ row }">
                <el-tag :type="getTaskTypeTag(row.task_type)">
                  {{ formatTaskType(row.task_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusTag(row.status)">
                  {{ formatStatus(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="160">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" class="mt-20">
      <!-- 快速操作 -->
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>快速操作</span>
          </template>
          
          <div class="quick-actions">
            <el-button type="primary" size="large" @click="$router.push('/pointclouds')">
              <el-icon class="mr-8"><Upload /></el-icon>
              上传点云
            </el-button>
            
            <el-button type="success" size="large" @click="$router.push('/scenes')">
              <el-icon class="mr-8"><Plus /></el-icon>
              创建场景
            </el-button>
            
            <el-button type="warning" size="large" @click="showHelp = true">
              <el-icon class="mr-8"><QuestionFilled /></el-icon>
              使用帮助
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 帮助对话框 -->
    <el-dialog v-model="showHelp" title="使用帮助" width="600px">
      <div class="help-content">
        <h4>快速开始</h4>
        <ol>
          <li>上传点云文件（支持 .ply, .las, .xyz 等格式）</li>
          <li>创建协同场景，邀请团队成员加入</li>
          <li>在场景中查看和处理点云数据</li>
          <li>使用处理任务进行滤波、分割、配准等操作</li>
        </ol>
        
        <h4>支持的功能</h4>
        <ul>
          <li>Voxel Grid 滤波 - 点云下采样</li>
          <li>统计滤波 - 去除离群点</li>
          <li>RANSAC 平面分割</li>
          <li>ICP 点云配准</li>
        </ul>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/services/api'

const loading = ref(false)
const showHelp = ref(false)

const stats = ref({
  pointCloudCount: 0,
  sceneCount: 0,
  taskCount: 0,
  totalSize: 0
})

const recentPointClouds = ref([])
const recentTasks = ref([])

const fetchStats = async () => {
  try {
    // 获取点云统计
    const pcResponse = await api.get('/pointclouds', { params: { page_size: 1 } })
    stats.value.pointCloudCount = pcResponse.data.data.total
    recentPointClouds.value = pcResponse.data.data.items.slice(0, 5)
    
    // 获取场景统计
    const sceneResponse = await api.get('/scenes', { params: { page_size: 1 } })
    stats.value.sceneCount = sceneResponse.data.data.total
    
    // 获取任务统计
    const taskResponse = await api.get('/tasks', { params: { page_size: 1 } })
    stats.value.taskCount = taskResponse.data.data.total
    recentTasks.value = taskResponse.data.data.items.slice(0, 5)
    
    // 计算总大小
    const allPCResponse = await api.get('/pointclouds', { params: { page_size: 1000 } })
    const totalSize = allPCResponse.data.data.items.reduce((sum: number, pc: any) => sum + (pc.file_size || 0), 0)
    stats.value.totalSize = totalSize
  } catch (error) {
    console.error('Failed to fetch stats:', error)
  }
}

const formatNumber = (num: number) => {
  return num?.toLocaleString() || '0'
}

const formatSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (date: string) => {
  return new Date(date).toLocaleString('zh-CN')
}

const formatTaskType = (type: string) => {
  const typeMap: Record<string, string> = {
    'filter_voxel': '体素滤波',
    'filter_statistical': '统计滤波',
    'segment_ransac': '平面分割',
    'register_icp': 'ICP配准'
  }
  return typeMap[type] || type
}

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    'pending': '待处理',
    'queued': '队列中',
    'running': '运行中',
    'completed': '已完成',
    'failed': '失败',
    'cancelled': '已取消'
  }
  return statusMap[status] || status
}

const getTaskTypeTag = (type: string) => {
  const typeMap: Record<string, any> = {
    'filter_voxel': 'primary',
    'filter_statistical': 'success',
    'segment_ransac': 'warning',
    'register_icp': 'danger'
  }
  return typeMap[type] || ''
}

const getStatusTag = (status: string) => {
  const statusMap: Record<string, any> = {
    'pending': 'info',
    'queued': '',
    'running': 'warning',
    'completed': 'success',
    'failed': 'danger',
    'cancelled': 'info'
  }
  return statusMap[status] || ''
}

onMounted(() => {
  fetchStats()
})
</script>

<style scoped lang="scss">
.dashboard-view {
  .mt-20 {
    margin-top: 20px;
  }
  
  .mr-8 {
    margin-right: 8px;
  }
  
  .stat-card {
    display: flex;
    align-items: center;
    padding: 10px;
    
    .stat-icon {
      width: 64px;
      height: 64px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      margin-right: 16px;
    }
    
    .stat-info {
      flex: 1;
      
      .stat-value {
        font-size: 28px;
        font-weight: 600;
        color: #1a1a1a;
        line-height: 1.2;
      }
      
      .stat-label {
        font-size: 14px;
        color: #666;
        margin-top: 4px;
      }
    }
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .quick-actions {
    display: flex;
    gap: 16px;
    
    .el-button {
      flex: 1;
    }
  }
  
  .help-content {
    h4 {
      margin: 16px 0 8px;
      color: #1a1a1a;
      
      &:first-child {
        margin-top: 0;
      }
    }
    
    ol, ul {
      padding-left: 20px;
      color: #666;
      line-height: 1.8;
    }
  }
}
</style>
