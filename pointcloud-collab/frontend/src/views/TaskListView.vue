<template>
  <div class="task-list-view">
    <div class="page-header">
      <h2>处理任务</h2>
      <el-button type="primary" @click="$router.push('/pointclouds')">
        <el-icon class="mr-8"><Plus /></el-icon>
        创建任务
      </el-button>
    </div>

    <el-card class="filter-card">
      <el-form :model="filterForm" inline>
        <el-form-item label="状态">
          <el-select v-model="filterForm.status" placeholder="全部状态" clearable>
            <el-option label="待处理" value="pending" />
            <el-option label="队列中" value="queued" />
            <el-option label="运行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="fetchTasks">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="list-card">
      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="task_name" label="任务名称" min-width="200" show-overflow-tooltip />

        <el-table-column prop="task_type" label="类型" width="130">
          <template #default="{ row }">
            <el-tag :type="getTaskTypeTag(row.task_type)" size="small">
              {{ formatTaskType(row.task_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTag(row.status)" size="small">
              {{ formatStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="progress" label="进度" width="150">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.progress)" :status="getProgressStatus(row.status)" />
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="viewDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="['pending', 'queued'].includes(row.status)"
              type="danger"
              link
              @click="cancelTask(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchTasks"
          @current-change="fetchTasks"
        />
      </div>
    </el-card>

    <!-- 任务详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="任务详情" width="600px">
      <el-descriptions :column="1" border v-if="selectedTask">
        <el-descriptions-item label="任务名称">{{ selectedTask.task_name }}</el-descriptions-item>
        <el-descriptions-item label="任务类型">{{ formatTaskType(selectedTask.task_type) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusTag(selectedTask.status)">
            {{ formatStatus(selectedTask.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="进度">
          <el-progress :percentage="Math.round(selectedTask.progress)" />
        </el-descriptions-item>
        <el-descriptions-item label="参数">
          <pre class="params-pre">{{ JSON.stringify(selectedTask.parameters, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="结果摘要" v-if="selectedTask.result_summary">
          <pre class="params-pre">{{ JSON.stringify(selectedTask.result_summary, null, 2) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" v-if="selectedTask.error_message">
          <span style="color: #f56c6c;">{{ selectedTask.error_message }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDate(selectedTask.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="开始时间" v-if="selectedTask.started_at">
          {{ formatDate(selectedTask.started_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="完成时间" v-if="selectedTask.completed_at">
          {{ formatDate(selectedTask.completed_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="实际耗时" v-if="selectedTask.actual_duration">
          {{ selectedTask.actual_duration }} 秒
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/services/api'

const loading = ref(false)
const tasks = ref([])
const showDetailDialog = ref(false)
const selectedTask = ref<any>(null)

const filterForm = reactive({
  status: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

const fetchTasks = async () => {
  loading.value = true
  try {
    const response = await api.get('/tasks', {
      params: {
        page: pagination.page,
        page_size: pagination.pageSize,
        status: filterForm.status
      }
    })
    tasks.value = response.data.data.items
    pagination.total = response.data.data.total
  } catch (error) {
    ElMessage.error('获取任务列表失败')
  } finally {
    loading.value = false
  }
}

const resetFilter = () => {
  filterForm.status = ''
  fetchTasks()
}

const viewDetail = (row: any) => {
  selectedTask.value = row
  showDetailDialog.value = true
}

const cancelTask = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要取消这个任务吗？', '提示', {
      type: 'warning'
    })

    await api.post(`/tasks/${row.id}/cancel`)
    ElMessage.success('任务已取消')
    fetchTasks()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.message || '取消失败')
    }
  }
}

const formatTaskType = (type: string) => {
  const typeMap: Record<string, string> = {
    'filter_voxel': '体素滤波',
    'filter_statistical': '统计滤波',
    'segment_ransac': '平面分割',
    'register_icp': 'ICP配准',
    'convert_format': '格式转换',
    'ai_detection': 'AI检测'
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
    'register_icp': 'danger',
    'convert_format': 'info',
    'ai_detection': ''
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

const getProgressStatus = (status: string) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return ''
}

const formatDate = (date: string) => {
  return date ? new Date(date).toLocaleString('zh-CN') : '-'
}

onMounted(() => {
  fetchTasks()
})
</script>

<style scoped lang="scss">
.task-list-view {
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

  .mr-8 {
    margin-right: 8px;
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

  .params-pre {
    margin: 0;
    padding: 8px;
    background: #f5f7fa;
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
  }
}
</style>
