import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true }
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { public: true }
    },
    {
      path: '/',
      name: 'Layout',
      component: () => import('@/views/LayoutView.vue'),
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('@/views/DashboardView.vue')
        },
        {
          path: 'pointclouds',
          name: 'PointClouds',
          component: () => import('@/views/PointCloudListView.vue')
        },
        {
          path: 'pointclouds/:id',
          name: 'PointCloudDetail',
          component: () => import('@/views/PointCloudDetailView.vue')
        },
        {
          path: 'scenes',
          name: 'Scenes',
          component: () => import('@/views/SceneListView.vue')
        },
        {
          path: 'scenes/:id',
          name: 'SceneDetail',
          component: () => import('@/views/SceneDetailView.vue')
        },
        {
          path: 'tasks',
          name: 'Tasks',
          component: () => import('@/views/TaskListView.vue')
        }
      ]
    }
  ]
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  
  if (!to.meta.public && !authStore.isAuthenticated) {
    next('/login')
  } else if (to.path === '/login' && authStore.isAuthenticated) {
    next('/')
  } else {
    next()
  }
})

export default router
