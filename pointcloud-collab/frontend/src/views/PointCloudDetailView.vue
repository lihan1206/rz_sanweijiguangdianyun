<template>
  <div class="pointcloud-detail-view">
    <el-page-header @back="$router.back()" title="点云详情" />
    
    <el-row :gutter="20" class="mt-20">
      <!-- 点云可视化 -->
      <el-col :span="16">
        <el-card>
          <PointCloudViewer
            v-if="pointCloudData"
            :points-url="pointCloudData.points_url"
            :colors-url="pointCloudData.colors_url"
            :point-info="pointInfo"
            :point-size="pointSize"
          />
          <el-empty v-else description="加载中..." />
        </el-card>
      </el-col>
      
      <!-- 点云信息 -->
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>基本信息</span>
          </template>
          
          <el-descriptions :column="1" border>
            <el-descriptions-item label="名称">{{ pointCloud?.name }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ pointCloud?.description || '-' }}</el-descriptions-item>
            <el-descriptions-item label="格式">{{ pointCloud?.file_format?.toUpperCase() }}</el-descriptions-item>
            <el-descriptions-item label="点数">{{ formatNumber(pointCloud?.point_count) }}</el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ formatSize(pointCloud?.file_size) }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="getStatusType(pointCloud?.status)">
                {{ formatStatus(pointCloud?.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="有颜色">{{ pointCloud?.has_color ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="有法线">{{ pointCloud?.has_normal ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="上传时间">{{ formatDate(pointCloud?.created_at) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
        
        <el-card class="mt-20">
          <template #header>
            <span>显示设置</span>
          </template>
          
          <el-form label-width="80px">
            <el-form-item label="点大小">
              <el-slider v-model="pointSize" :min="0.1" :max="5" :step="0.1" />
            </el-form-item>
          </el-form>
        </el-card>
        
        <el-card class="mt-20">
          <template #header>
            <span>操作</span>
          </template>
          
          <el-button type="primary" @click="showProcessDialog = true">
            创建处理任务
          </el-button>
          <el-button @click="handleExport">导出</el-button>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 处理对话框 -->
    <el-dialog v-model="showProcessDialog" title="创建处理任务" width="500px">
      <el-form :model="processForm" label-width="100px">
        <el-form-item label="任务类型">
          <el-select v-model="processForm.task_type" placeholder="选择任务类型">
            <el-option label="Voxel Grid 滤波" value="filter_voxel" />
            <el-option label="统计滤波" value="filter_statistical" />
            <el-option label="RANSAC 平面分割" value="segment_ransac" />
            <el-option label="ICP 配准" value="register_icp" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="任务名称">
          <el-input v-model="processForm.task_name" placeholder="任务名称" />
        </el-form-item>
        
        <!-- 动态参数表单 -->
        <template v-if="processForm.task_type === 'filter_voxel'">
          <el-form-item label="体素大小">
            <el-input-number v-model="processForm.parameters.voxel_size" :min="0.001" :step="0.01" />
          </el-form-item>
        </template>
        
        <template v-if="processForm.task_type === 'filter_statistical'">
          <el-form-item label="邻域点数">
            <el-input-number v-model="processForm.parameters.nb_neighbors" :min="1" />
          </el-form-item>
          <el-form-item label="标准差倍数">
            <el-input-number v-model="processForm.parameters.std_ratio" :min="0.1" :step="0.1" />
          </el-form-item>
        </template>
      </el-form>
      
      <template #footer>
        <el-button @click="showProcessDialog = false">取消</el-button>
        <el-button type="primary" @click="createTask" :loading="processing">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/services/api'
import PointCloudViewer from '@/components/PointCloudViewer.vue'

const route = useRoute()
const router = useRouter()
const pointCloudId = route.params.id as string

const pointCloud = ref<any>(null)
const pointCloudData = ref<any>(null)
const pointSize = ref(1)
const showProcessDialog = ref(false)
const processing = ref(false)

const pointInfo = ref({
  pointCount: 0,
  boundingBox: { min: [0, 0, 0], max: [0, 0, 0] },
  hasColor: false,
  hasNormal: false
})

const processForm = ref({
  task_type: 'filter_voxel',
  task_name: '',
  parameters: {
    voxel_size: 0.05,
    nb_neighbors: 20,
    std_ratio: 2.0
  }
})

const fetchPointCloudDetail = async () => {
  try {
    const response = await api.get(`/pointclouds/${pointCloudId}`)
    pointCloud.value = response.data.data
    
    // 更新点云信息
    pointInfo.value = {
      pointCount: pointCloud.value.point_count,
      boundingBox: pointCloud.value.bounding_box,
      hasColor: pointCloud.value.has_color,
      hasNormal: pointCloud.value.has_normal
    }
  } catch (error) {
    ElMessage.error('获取点云详情失败')
  }
}

const fetchPointCloudData = async () => {
  try {
    const response = await api.get(`/pointclouds/${pointCloudId}/data`)
    pointCloudData.value = response.data.data
  } catch (error) {
    ElMessage.error('获取点云数据失败')
  }
}

const createTask = async () => {
  processing.value = true
  try {
    const params: any = {}
    
    if (processForm.value.task_type === 'filter_voxel') {
      params.voxel_size = processForm.value.parameters.voxel_size
    } else if (processForm.value.task_type === 'filter_statistical') {
      params.nb_neighbors = processForm.value.parameters.nb_neighbors
      params.std_ratio = processForm.value.parameters.std_ratio
    }
    
    await api.post('/tasks', {
      point_cloud_id: parseInt(pointCloudId),
      task_type: processForm.value.task_type,
      task_name: processForm.value.task_name,
      parameters: params
    })
    
    ElMessage.success('任务创建成功')
    showProcessDialog.value = false
    router.push('/tasks')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '创建任务失败')
  } finally {
    processing.value = false
  }
}

const handleExport = () => {
  ElMessage.info('导出功能开发中')
}

const formatNumber = (num: number) => {
  return num?.toLocaleString() || '0'
}

const formatSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (date: string) => {
  return date ? new Date(date).toLocaleString('zh-CN') : '-'
}

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    'ready': '就绪',
    'processing': '处理中',
    'uploading': '上传中',
    'error': '错误'
  }
  return statusMap[status] || status
}

const getStatusType = (status: string) => {
  const typeMap: Record<string, any> = {
    'ready': 'success',
    'processing': 'warning',
    'uploading': 'info',
    'error': 'danger'
  }
  return typeMap[status] || ''
}

onMounted(() => {
  fetchPointCloudDetail()
  fetchPointCloudData()
})
</script>

<style scoped lang="scss">
.pointcloud-detail-view {
  .mt-20 {
    margin-top: 20px;
  }
  
  :deep(.el-page-header) {
    margin-bottom: 20px;
  }
}
</style>
