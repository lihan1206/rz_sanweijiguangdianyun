<template>
  <div class="scene-list-view">
    <div class="page-header">
      <h2>协同场景</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon class="mr-8"><Plus /></el-icon>
        创建场景
      </el-button>
    </div>
    
    <el-row :gutter="20">
      <el-col :span="8" v-for="scene in scenes" :key="scene.id">
        <el-card class="scene-card" shadow="hover" @click="enterScene(scene)">
          <div class="scene-header">
            <h3>{{ scene.name }}</h3>
            <el-tag :type="getVisibilityType(scene.visibility)" size="small">
              {{ formatVisibility(scene.visibility) }}
            </el-tag>
          </div>
          
          <p class="scene-description">{{ scene.description || '暂无描述' }}</p>
          
          <div class="scene-stats">
            <span>
              <el-icon><UserFilled /></el-icon>
              {{ scene.member_count }} 成员
            </span>
            <span>
              <el-icon><DataAnalysis /></el-icon>
              {{ scene.point_cloud_count }} 点云
            </span>
          </div>
          
          <div class="scene-footer">
            <span class="scene-owner">创建者: {{ scene.owner?.username }}</span>
            <span class="scene-time">{{ formatDate(scene.created_at) }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 创建场景对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建场景" width="500px">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="场景名称" />
        </el-form-item>
        
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" placeholder="场景描述" />
        </el-form-item>
        
        <el-form-item label="可见性">
          <el-radio-group v-model="createForm.visibility">
            <el-radio label="private">私有</el-radio>
            <el-radio label="shared">共享</el-radio>
            <el-radio label="public">公开</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="最大成员">
          <el-input-number v-model="createForm.max_members" :min="1" :max="50" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createScene" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
    
    <!-- 加入场景对话框 -->
    <el-dialog v-model="showJoinDialog" title="加入场景" width="400px">
      <el-form :model="joinForm" label-width="80px">
        <el-form-item label="邀请码">
          <el-input v-model="joinForm.invite_code" placeholder="输入邀请码" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showJoinDialog = false">取消</el-button>
        <el-button type="primary" @click="joinScene" :loading="joining">加入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/services/api'

const router = useRouter()

const scenes = ref([])
const showCreateDialog = ref(false)
const showJoinDialog = ref(false)
const creating = ref(false)
const joining = ref(false)
const createFormRef = ref()

const createForm = reactive({
  name: '',
  description: '',
  visibility: 'private',
  max_members: 10
})

const createRules = {
  name: [
    { required: true, message: '请输入场景名称', trigger: 'blur' },
    { max: 100, message: '名称最多100个字符', trigger: 'blur' }
  ]
}

const joinForm = reactive({
  scene_id: 0,
  invite_code: ''
})

const fetchScenes = async () => {
  try {
    const response = await api.get('/scenes')
    scenes.value = response.data.data.items
  } catch (error) {
    ElMessage.error('获取场景列表失败')
  }
}

const createScene = async () => {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  
  creating.value = true
  try {
    const response = await api.post('/scenes', createForm)
    ElMessage.success('场景创建成功')
    showCreateDialog.value = false
    
    // 复制邀请码
    const inviteCode = response.data.data.invite_code
    await navigator.clipboard.writeText(inviteCode)
    ElMessage.success(`邀请码已复制: ${inviteCode}`)
    
    fetchScenes()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

const joinScene = async () => {
  if (!joinForm.invite_code) {
    ElMessage.warning('请输入邀请码')
    return
  }
  
  joining.value = true
  try {
    await api.post(`/scenes/${joinForm.scene_id}/join`, {
      invite_code: joinForm.invite_code
    })
    ElMessage.success('加入场景成功')
    showJoinDialog.value = false
    fetchScenes()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.message || '加入失败')
  } finally {
    joining.value = false
  }
}

const enterScene = (scene: any) => {
  router.push(`/scenes/${scene.id}`)
}

const formatVisibility = (visibility: string) => {
  const map: Record<string, string> = {
    'private': '私有',
    'shared': '共享',
    'public': '公开'
  }
  return map[visibility] || visibility
}

const getVisibilityType = (visibility: string) => {
  const map: Record<string, any> = {
    'private': 'info',
    'shared': 'warning',
    'public': 'success'
  }
  return map[visibility] || ''
}

const formatDate = (date: string) => {
  return new Date(date).toLocaleDateString('zh-CN')
}

onMounted(() => {
  fetchScenes()
})
</script>

<style scoped lang="scss">
.scene-list-view {
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
  
  .scene-card {
    cursor: pointer;
    transition: transform 0.2s;
    margin-bottom: 20px;
    
    &:hover {
      transform: translateY(-4px);
    }
    
    .scene-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      
      h3 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
      }
    }
    
    .scene-description {
      color: #666;
      font-size: 14px;
      margin-bottom: 16px;
      min-height: 40px;
    }
    
    .scene-stats {
      display: flex;
      gap: 16px;
      margin-bottom: 12px;
      color: #666;
      font-size: 14px;
      
      span {
        display: flex;
        align-items: center;
        gap: 4px;
      }
    }
    
    .scene-footer {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: #999;
    }
  }
}
</style>
