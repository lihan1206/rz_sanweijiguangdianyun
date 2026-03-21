<template>
  <el-container class="layout-container">
    <el-aside width="240px" class="sidebar">
      <div class="logo">
        <el-icon :size="32"><DataAnalysis /></el-icon>
        <span>点云协同系统</span>
      </div>
      
      <el-menu
        :default-active="$route.path"
        router
        class="sidebar-menu"
        background-color="#1a1a2e"
        text-color="#a0a0a0"
        active-text-color="#fff"
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        
        <el-menu-item index="/pointclouds">
          <el-icon><DataAnalysis /></el-icon>
          <span>点云管理</span>
        </el-menu-item>
        
        <el-menu-item index="/scenes">
          <el-icon><UserFilled /></el-icon>
          <span>协同场景</span>
        </el-menu-item>
        
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <span>处理任务</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <breadcrumb />
        </div>
        
        <div class="header-right">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" :icon="UserFilled" />
              <span class="username">{{ authStore.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人资料</el-dropdown-item>
                <el-dropdown-item command="settings">系统设置</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const handleCommand = async (command: string) => {
  switch (command) {
    case 'profile':
      // TODO: 个人资料页面
      break
    case 'settings':
      // TODO: 系统设置页面
      break
    case 'logout':
      try {
        await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        })
        
        await authStore.logout()
        ElMessage.success('已退出登录')
        router.push('/login')
      } catch {
        // 用户取消
      }
      break
  }
}
</script>

<style scoped lang="scss">
.layout-container {
  height: 100vh;
  
  .sidebar {
    background: #1a1a2e;
    
    .logo {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      color: #fff;
      font-size: 18px;
      font-weight: 600;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .sidebar-menu {
      border-right: none;
      
      :deep(.el-menu-item) {
        &:hover {
          background-color: rgba(255, 255, 255, 0.05);
        }
        
        &.is-active {
          background-color: #409eff;
        }
      }
    }
  }
  
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #fff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    
    .header-right {
      .user-info {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 4px;
        transition: background-color 0.3s;
        
        &:hover {
          background-color: #f5f5f5;
        }
        
        .username {
          font-size: 14px;
          color: #333;
        }
      }
    }
  }
  
  .main-content {
    background: #f5f7fa;
    padding: 20px;
    overflow-y: auto;
  }
}
</style>
