<template>
  <div class="scene-detail-view">
    <el-page-header @back="$router.back()">
      <template #content>
        <span class="scene-title">{{ scene?.name }}</span>
        <el-tag :type="getVisibilityType(scene?.visibility)" size="small" class="ml-12">
          {{ formatVisibility(scene?.visibility) }}
        </el-tag>
      </template>
      <template #extra>
        <el-button @click="showInviteDialog = true">
          <el-icon class="mr-8"><Share /></el-icon>
          邀请成员
        </el-button>
      </template>
    </el-page-header>
    
    <el-row :gutter="20" class="mt-20">
      <!-- 协同视图 -->
      <el-col :span="18">
        <el-card class="collab-viewer">
          <template #header>
            <div class="viewer-header">
              <span>协同视图</span>
              <div class="active-users">
                <span>在线用户:</span>
                <el-avatar
                  v-for="user in activeUsers"
                  :key="user.id"
                  :size="24"
                  :title="user.username"
                  class="user-avatar"
                >
                  {{ user.username[0] }}
                </el-avatar>
              </div>
            </div>
          </template>
          
          <div class="viewer-placeholder">
            <el-empty description="协同可视化区域">
              <template #description>
                <p>协同可视化区域</p>
                <p class="text-secondary">显示场景中所有用户的点云</p>
              </template>
            </el-empty>
          </div>
        </el-card>
      </el-col>
      
      <!-- 场景信息 -->
      <el-col :span="6">
        <el-card>
          <template #header>
            <span>场景点云</span>
          </template>
          
          <el-empty v-if="!scenePointClouds.length" description="暂无点云" />
          
          <div v-else class="pointcloud-list">
            <div
              v-for="pc in scenePointClouds"
              :key="pc.id"
              class="pointcloud-item"
            >
              <div class="pc-info">
                <el-checkbox v-model="pc.visible" @change="toggleVisibility(pc)">
                  {{ pc.name }}
                </el-checkbox>
                <span class="pc-owner">by {{ pc.owner.username }}</span>
              </div>
              <el-tag size="small" :type="getStatusType(pc.status)">
                {{ formatStatus(pc.status) }}
              </el-tag>
            </div>
          </div>
        </el-card>
        
        <el-card class="mt-20">
          <template #header>
            <span>成员列表</span>
          </template>
          
          <el-empty v-if="!members.length" description="暂无成员" />
          
          <div v-else class="member-list">
            <div
              v-for="member in members"
              :key="member.id"
              class="member-item"
            >
              <el-avatar :size="32" :src="member.user?.avatar_url">
                {{ member.user?.username[0] }}
              </el-avatar>
              <div class="member-info">
                <span class="member-name">{{ member.user?.username }}</span>
                <el-tag size="small" :type="getRoleType(member.role)">
                  {{ formatRole(member.role) }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
        
        <el-card class="mt-20">
          <template #header>
            <span>聊天</span>
          </template>
          
          <div class="chat-container">
            <div class="chat-messages" ref="chatMessagesRef">
              <div
                v-for="(msg, index) in chatMessages"
                :key="index"
                class="chat-message"
              >
                <span class="chat-user">{{ msg.user }}:</span>
                <span class="chat-text">{{ msg.text }}</span>
              </div>
            </div>
            
            <el-input
              v-model="chatInput"
              placeholder="发送消息..."
              @keyup.enter="sendMessage"
            >
              <template #append>
                <el-button @click="sendMessage">发送</el-button>
              </template>
            </el-input>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 邀请对话框 -->
    <el-dialog v-model="showInviteDialog" title="邀请成员" width="400px">
      <div class="invite-content">
        <p>分享邀请码给团队成员：</p>
        <div class="invite-code">
          <code>{{ scene?.invite_code }}</code>
          <el-button type="primary" link @click="copyInviteCode">
            <el-icon><CopyDocument /></el-icon>
            复制
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/services/api'
import { wsService } from '@/services/websocket'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const sceneId = parseInt(route.params.id as string)

const scene = ref<any>(null)
const scenePointClouds = ref<any[]>([])
const members = ref<any[]>([])
const activeUsers = ref<any[]>([])
const showInviteDialog = ref(false)
const chatMessages = ref<any[]>([])
const chatInput = ref('')

const fetchSceneDetail = async () => {
  try {
    const response = await api.get(`/scenes/${sceneId}`)
    scene.value = response.data.data
  } catch (error) {
    ElMessage.error('获取场景详情失败')
  }
}

const fetchScenePointClouds = async () => {
  try {
    const response = await api.get(`/scenes/${sceneId}/pointclouds`)
    scenePointClouds.value = response.data.data.point_clouds
  } catch (error) {
    ElMessage.error('获取场景点云失败')
  }
}

const fetchMembers = async () => {
  try {
    const response = await api.get(`/scenes/${sceneId}/members`)
    members.value = response.data.data.members
  } catch (error) {
    ElMessage.error('获取成员列表失败')
  }
}

const connectWebSocket = async () => {
  if (!authStore.accessToken) return
  
  try {
    await wsService.connect(sceneId, authStore.accessToken)
    
    // 监听事件
    wsService.on('user:joined', (data) => {
      ElMessage.info(`${data.username} 加入了场景`)
      activeUsers.value.push(data)
    })
    
    wsService.on('user:left', (data) => {
      activeUsers.value = activeUsers.value.filter(u => u.id !== data.user_id)
    })
    
    wsService.on('scene:users', (data) => {
      activeUsers.value = data.active_users
    })
    
    wsService.on('pointcloud:uploaded', (data) => {
      ElMessage.success(`新点云上传: ${data.name}`)
      fetchScenePointClouds()
    })
    
    wsService.on('task:completed', (data) => {
      ElMessage.success('处理任务完成')
      fetchScenePointClouds()
    })
  } catch (error) {
    console.error('WebSocket connection failed:', error)
  }
}

const toggleVisibility = (pc: any) => {
  wsService.updatePointCloudVisibility(pc.id, pc.visible)
}

const sendMessage = () => {
  if (!chatInput.value.trim()) return
  
  chatMessages.value.push({
    user: authStore.user?.username,
    text: chatInput.value
  })
  
  chatInput.value = ''
}

const copyInviteCode = () => {
  navigator.clipboard.writeText(scene.value?.invite_code)
  ElMessage.success('邀请码已复制')
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

const formatStatus = (status: string) => {
  const map: Record<string, string> = {
    'ready': '就绪',
    'processing': '处理中',
    'uploading': '上传中'
  }
  return map[status] || status
}

const getStatusType = (status: string) => {
  const map: Record<string, any> = {
    'ready': 'success',
    'processing': 'warning',
    'uploading': 'info'
  }
  return map[status] || ''
}

const formatRole = (role: string) => {
  const map: Record<string, string> = {
    'owner': '所有者',
    'editor': '编辑者',
    'viewer': '查看者'
  }
  return map[role] || role
}

const getRoleType = (role: string) => {
  const map: Record<string, any> = {
    'owner': 'danger',
    'editor': 'warning',
    'viewer': 'info'
  }
  return map[role] || ''
}

onMounted(() => {
  fetchSceneDetail()
  fetchScenePointClouds()
  fetchMembers()
  connectWebSocket()
})

onUnmounted(() => {
  wsService.disconnect()
})
</script>

<style scoped lang="scss">
.scene-detail-view {
  .scene-title {
    font-size: 20px;
    font-weight: 600;
  }
  
  .ml-12 {
    margin-left: 12px;
  }
  
  .mt-20 {
    margin-top: 20px;
  }
  
  .mr-8 {
    margin-right: 8px;
  }
  
  .collab-viewer {
    .viewer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      .active-users {
        display: flex;
        align-items: center;
        gap: 8px;
        
        .user-avatar {
          margin-left: -8px;
          border: 2px solid #fff;
          
          &:first-child {
            margin-left: 0;
          }
        }
      }
    }
    
    .viewer-placeholder {
      height: 600px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f5f7fa;
      border-radius: 8px;
      
      .text-secondary {
        color: #999;
        font-size: 14px;
      }
    }
  }
  
  .pointcloud-list {
    .pointcloud-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0;
      border-bottom: 1px solid #eee;
      
      &:last-child {
        border-bottom: none;
      }
      
      .pc-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
        
        .pc-owner {
          font-size: 12px;
          color: #999;
        }
      }
    }
  }
  
  .member-list {
    .member-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 0;
      
      .member-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
        
        .member-name {
          font-size: 14px;
        }
      }
    }
  }
  
  .chat-container {
    .chat-messages {
      height: 200px;
      overflow-y: auto;
      margin-bottom: 12px;
      padding: 8px;
      background: #f5f7fa;
      border-radius: 4px;
      
      .chat-message {
        margin-bottom: 8px;
        
        .chat-user {
          font-weight: 600;
          color: #409eff;
          margin-right: 8px;
        }
        
        .chat-text {
          color: #333;
        }
      }
    }
  }
  
  .invite-content {
    p {
      margin-bottom: 16px;
      color: #666;
    }
    
    .invite-code {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      background: #f5f7fa;
      border-radius: 4px;
      
      code {
        flex: 1;
        font-size: 18px;
        font-weight: 600;
        color: #409eff;
        letter-spacing: 2px;
      }
    }
  }
}
</style>
