import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import Cookies from 'js-cookie'
import api from '@/services/api'

interface User {
  id: number
  username: string
  email: string
  role: string
}

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
}

export const useAuthStore = defineStore('auth', () => {
  // State
  const accessToken = ref<string | null>(Cookies.get('access_token') || null)
  const refreshToken = ref<string | null>(Cookies.get('refresh_token') || null)
  const user = ref<User | null>(null)

  // Getters
  const isAuthenticated = computed(() => !!accessToken.value)
  
  const getAuthHeaders = computed(() => ({
    Authorization: `Bearer ${accessToken.value}`
  }))

  // Actions
  const setTokens = (access: string, refresh: string) => {
    accessToken.value = access
    refreshToken.value = refresh
    Cookies.set('access_token', access, { expires: 1/24 }) // 1小时
    Cookies.set('refresh_token', refresh, { expires: 7 }) // 7天
  }

  const clearTokens = () => {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    Cookies.remove('access_token')
    Cookies.remove('refresh_token')
  }

  const login = async (username: string, password: string) => {
    const response = await api.post('/auth/login', { username, password })
    const { access_token, refresh_token, user: userData } = response.data.data
    
    setTokens(access_token, refresh_token)
    user.value = userData
    
    return response.data
  }

  const register = async (username: string, email: string, password: string, fullName?: string) => {
    const response = await api.post('/auth/register', {
      username,
      email,
      password,
      full_name: fullName
    })
    return response.data
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout', null, {
        headers: getAuthHeaders.value
      })
    } finally {
      clearTokens()
    }
  }

  const fetchUser = async () => {
    if (!accessToken.value) return
    
    try {
      const response = await api.get('/auth/me', {
        headers: getAuthHeaders.value
      })
      user.value = response.data.data
    } catch (error) {
      clearTokens()
      throw error
    }
  }

  const refreshAccessToken = async () => {
    if (!refreshToken.value) {
      clearTokens()
      throw new Error('No refresh token')
    }
    
    try {
      const response = await api.post('/auth/refresh', null, {
        headers: { Authorization: `Bearer ${refreshToken.value}` }
      })
      const { access_token } = response.data.data
      accessToken.value = access_token
      Cookies.set('access_token', access_token, { expires: 1/24 })
      return access_token
    } catch (error) {
      clearTokens()
      throw error
    }
  }

  // 初始化时获取用户信息
  if (accessToken.value) {
    fetchUser()
  }

  return {
    accessToken,
    refreshToken,
    user,
    isAuthenticated,
    getAuthHeaders,
    login,
    register,
    logout,
    fetchUser,
    refreshAccessToken,
    clearTokens
  }
})
