<template>
  <div class="pointcloud-list-view">
    <div class="page-header">
      <h2>点云管理</h2>
      <el-button type="primary" @click="showUploadDialog = true">
        <el-icon class="mr-8"><Upload /></el-icon>
        上传点云
      </el-button>
    </div>
    
    <!-- 搜索和筛选 -->
    <el-card class="filter-card">
      <el-form :model="filterForm" inline>
        <el-form-item label="搜索">
          <el-input
            v-model="filterForm.search"
            placeholder="搜索名称或描述"
            clearable
            @keyup.enter="fetchPointClouds"
          />
        </el-form-item>
        
        <el-form-item label="状态">
          <el-select v-model="filterForm.status" placeholder="全部状态" clearable>
            <el-option label="就绪" value="ready" />
            <el-option label="处理中" value="processing" />
            <el-option label="上传中" value="uploading" />
            <el-option label="错误" value="error" />
          </el-select>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="fetchPointClouds">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 点云列表 -->
    <el-card class="list-card">
      <el-table :data="pointClouds" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="viewDetail(row)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        
        <el-table-column prop="file_format" label="格式" width="80">
          <template #default="{ row }">
            <el-tag size="small">{{ row.file_format?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="point_count" label="点数" width="120">
          <template #default="{ row }">
            {{ formatNumber(row.point_count) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="file_size" label="大小" width="100">
          <template #default="{ row }">
            {{ formatSize(row.file_size) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ formatStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="上传时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="viewDetail(row)">
              查看
            </el-button>
            <el-button type="primary" link @click="showProcessDialog(row)">
              处理
            </el-button>
            <el-button type="danger" link @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchPointClouds"
          @current-change="fetchPointClouds"
        />
      </div>
    </el-card>
    
    <!-- 上传对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传点云" width="500px">
      <el-upload
        ref="uploadRef"
        drag
        action="/api/v1/pointclouds/upload"
        :headers="uploadHeaders"
        :data="uploadData"
        :before-upload="beforeUpload"
        :on-success="handleUploadSuccess"
        :on-error="handleUploadError"
        accept=".ply,.las,.laz,.xyz,.pcd,.obj"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持格式: .ply, .las, .laz, .xyz, .pcd, .obj
            <br>
            单个文件最大 500MB
          </div>
        </template>
      </el-upload>
      
      <el-form :model="uploadData" label-width="80px" class="mt-16">
        <el-form-item label="名称">
          <el-input v-model="uploadData.name" placeholder="点云名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="uploadData.description" type="textarea" placeholder="描述" />
        </el-form-item>
        <el-form-item label="可见性">
          <el-radio-group v-model="uploadData.visibility">
            <el-radio label="private">私有</el-radio>
            <el-radio label="public">公开</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </el-dialog>
    
    <!-- 处理对话框 -->
    <el-dialog v-model="showProcessDlg" title="创建处理任务" width="500px">
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
        
        <!-- Voxel Grid 参数 -->
        <template v-if="processForm.task_type === 'filter_voxel'">
          <el-form-item label="体素大小">
            <el-input-number v-model="processForm.parameters.voxel_size" :min="0.001" :step="0.01" />
          </el-form-item>
        </template>
        
        <!-- 统计滤波参数 -->
        <template v-if="processForm.task_type === 'filter_statistical'">
          <el-form-item label="邻域点数">
            <el-input-number v-model="processForm.parameters.nb_neighbors" :min="1" />
          </el-form-item>
          <el-form-item label="标准差倍数">
            <el-input-number v-model="processForm.parameters.std_ratio" :min="0.1" :step="0.1" />
          </el-form-item>
        </template>
        
        <!-- RANSAC 参数 -->
        <template v-if="processForm.task_type === 'segment_ransac'">
          <el-form-item label="距离阈值">
            <el-input-number v-model="processForm.parameters.distance_threshold" :min="0.0001" :step="0.001" />
          </el-form-item>
          <el-form-item label="迭代次数">
            <el-input-number v-model="processForm.parameters.num_iterations" :min="1" />
          </el-form-item>
        </template>
        
        <!-- ICP 参数 -->
        <template v-if="processForm.task_type === 'register_icp'">
          <el-form-item label="目标点云">
            <el-select v-model="processForm.parameters.target_point_cloud_id" placeholder="选择目标点云">
              <el-option
                v-for="pc in pointClouds"
                :key="pc.id"
                :label="pc.name"
                :value="pc.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="最大对应距离">
            <el-input-number v-model="processForm.parameters.max_correspondence_distance" :min="0.001" :step="0.01" />
          </el-form-item>
        </template>
      </el-form>
      
      <template #footer>
        <el-button @click="showProcessDlg = false">取消</el-button>
        <el-button type="primary" @click="createTask" :loading="processing">
          创建任务
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const pointClouds = ref([])
const showUploadDialog = ref(false)
const showProcessDlg = ref(false)
const processing = ref(false)
const selectedPointCloud = ref<any>(null)

const filterForm = reactive({
  search: '',
  status: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${authStore.accessToken}`
}))

const uploadData = reactive({
  name: '',
  description: '',
  visibility: 'private'
})

const processForm = reactive({
  point_cloud_id: 0,
  task_type: 'filter_voxel',
  task_name: '',
  parameters: {
    voxel_size: 0.05,
    nb_neighbors: 20,
    std_ratio: 2.0,
    distance_threshold: 0.01,
    num_iterations: 1000,
    target_point_cloud_id: null,
    max_correspondence_distance: 0.05
  }
})

const fetchPointClouds = async () => {
  loading.value = true
  try {
    const response = await api.get('/pointclouds', {
      params: {
        page: pagination.page,
        page_size: pagination.pageSize,
        search: filterForm.search,
        status: filterForm.status
      }
    })
    pointClouds.value = response.data.data.items
    pagination.total = response.data.data.total
  } catch (error) {
    ElMessage.error('获取点云列表失败')
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filterForm.search = ''
  filterForm.status = ''
  fetchPointClouds()
}

const beforeUpload = (file: File) => {
  const validTypes = ['.ply', '.las', '.laz', '.xyz', '.pcd', '.obj']
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  
  if (!validTypes.includes(ext)) {
    ElMessage.error('不支持的文件格式')
    return false
  }
  
  if (file.size > 500 * 1024 * 1024) {
    ElMessage.error('文件大小超过500MB限制')
    return false
  }
  
  return true
}

const handleUploadSuccess = () => {
  ElMessage.success('上传成功')
  showUploadDialog.value = false
  fetchPointClouds()
}

const handleUploadError = (error: any) => {
  ElMessage.error(error.message || '上传失败')
}

const viewDetail = (row: any) => {
  router.push(`/pointclouds/${row.id}`)
}

const showProcessDialog = (row: any) => {
  selectedPointCloud.value = row
  processForm.point_cloud_id = row.id
  processForm.task_name = `${row.name}_处理`
  showProcessDlg.value = true
}

const createTask = async () => {
  processing.value = true
  try {
    const params: any = {}
    
    switch (processForm.task_type) {
      case 'filter_voxel':
        params.voxel_size = processForm.parameters.voxel_size
        break
      case 'filter_statistical':
        params.nb_neighbors = processForm.parameters.nb_neighbors
        params.std_ratio = processForm.parameters.std_ratio
        break
      case 'segment_ransac':
        params.distance_threshold = processForm.parameters.distance_threshold
        params.num_iterations = processForm.parameters.num_iterations
        break
      case 'register_icp':
        params.target_point_cloud_id = processForm.parameters.target_point_cloud_id
        params.max_correspondence_distance = processForm.parameters.max_correspondence_distance
        break
    }
    
    await api.post('/tasks', {
      point_cloud_id: processForm.point_cloud_id,
      task_type: processForm.task_type,
      task_name: processForm.task_name,
      parameters: params
    })
    
    ElMessage.success('任务创建成功')
    showProcessDlg.value = false
    router.push('/tasks')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '创建任务失败')
  } finally {
    processing.value = false
  }
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要删除这个点云吗？', '提示', {
      type: 'warning'
    })
    
    await api.delete(`/pointclouds/${row.id}`)
    ElMessage.success('删除成功')
    fetchPointClouds()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.message || '删除失败')
    }
  }
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
  return new Date(date).toLocaleString('zh-CN')
}

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    'ready': '就绪',
    'processing': '处理中',
    'uploading': '上传中',
    'error': '错误',
    'deleted': '已删除'
  }
  return statusMap[status] || status
}

const getStatusType = (status: string) => {
  const typeMap: Record<string, any> = {
    'ready': 'success',
    'processing': 'warning',
    'uploading': 'info',
    'error': 'danger',
    'deleted': 'info'
  }
  return typeMap[status] || ''
}

onMounted(() => {
  fetchPointClouds()
})
</script>

<style scoped lang="scss">
.pointcloud-list-view {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    
    h2 {
      margin: 0;
      font-size: 24px;
      font-weight: 600;
    }
  }
  
  .filter-card {
    margin-bottom: 20px;
  }
  
  .list-card {
    .pagination-container {
      display: flex;
      justify-content: flex-end;
      margin-top: 20px;
    }
  }
  
  .mr-8 {
    margin-right: 8px;
  }
  
  .mt-16 {
    margin-top: 16px;
  }
}
</style>
