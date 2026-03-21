# 错误处理方案

## 1. 错误分类

### 1.1 系统级错误
- **数据库连接失败**
- **Redis连接失败**
- **文件系统错误**
- **内存不足**

### 1.2 应用级错误
- **认证错误** (401 Unauthorized)
- **权限错误** (403 Forbidden)
- **资源不存在** (404 Not Found)
- **请求参数错误** (400 Bad Request)
- **业务逻辑错误** (422 Unprocessable Entity)

### 1.3 文件上传错误
- **文件格式不支持**
- **文件大小超限**
- **文件损坏**
- **上传中断**
- **存储空间不足**

### 1.4 处理任务错误
- **任务超时**
- **处理失败**
- **资源不足**
- **算法错误**

## 2. 错误处理机制

### 2.1 全局异常处理

```python
# app/core/exceptions.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

class PointCloudException(Exception):
    """基础异常类"""
    def __init__(self, message: str, code: str = None, status_code: int = 500):
        self.message = message
        self.code = code or "INTERNAL_ERROR"
        self.status_code = status_code
        super().__init__(self.message)

class AuthenticationError(PointCloudException):
    """认证错误"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, "AUTH_ERROR", 401)

class AuthorizationError(PointCloudException):
    """授权错误"""
    def __init__(self, message: str = "权限不足"):
        super().__init__(message, "FORBIDDEN", 403)

class ResourceNotFoundError(PointCloudException):
    """资源不存在"""
    def __init__(self, resource: str = "资源"):
        super().__init__(f"{resource}不存在", "NOT_FOUND", 404)

class ValidationError(PointCloudException):
    """验证错误"""
    def __init__(self, message: str = "参数验证失败"):
        super().__init__(message, "VALIDATION_ERROR", 400)

class FileUploadError(PointCloudException):
    """文件上传错误"""
    def __init__(self, message: str = "文件上传失败"):
        super().__init__(message, "UPLOAD_ERROR", 400)

class ProcessingError(PointCloudException):
    """处理错误"""
    def __init__(self, message: str = "处理失败"):
        super().__init__(message, "PROCESSING_ERROR", 500)

class TaskTimeoutError(PointCloudException):
    """任务超时"""
    def __init__(self, message: str = "任务处理超时"):
        super().__init__(message, "TIMEOUT_ERROR", 504)
```

### 2.2 异常处理器

```python
# app/core/exception_handlers.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .exceptions import PointCloudException
import logging

logger = logging.getLogger(__name__)

async def pointcloud_exception_handler(request: Request, exc: PointCloudException):
    """处理自定义异常"""
    logger.error(f"Exception: {exc.code} - {exc.message}", exc_info=True)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.message,
            "data": None,
            "error": {
                "code": exc.code,
                "details": str(exc)
            }
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理验证错误"""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(f"Validation error: {errors}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": 422,
            "message": "参数验证失败",
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "details": errors
            }
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    """处理通用异常"""
    logger.exception("Unhandled exception")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "details": str(exc) if app.debug else "请联系管理员"
            }
        }
    )
```

### 2.3 注册异常处理器

```python
# app/main.py
from fastapi import FastAPI
from app.core.exceptions import PointCloudException
from app.core.exception_handlers import (
    pointcloud_exception_handler,
    validation_exception_handler,
    general_exception_handler
)
from fastapi.exceptions import RequestValidationError

app = FastAPI()

# 注册异常处理器
app.add_exception_handler(PointCloudException, pointcloud_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
```

## 3. 具体错误场景处理

### 3.1 文件上传失败处理

```python
# 错误类型与处理策略
UPLOAD_ERROR_HANDLERS = {
    "FILE_TOO_LARGE": {
        "code": "FILE_TOO_LARGE",
        "message": "文件大小超过限制（最大500MB）",
        "status_code": 413,
        "solution": "请压缩文件或分批上传"
    },
    "UNSUPPORTED_FORMAT": {
        "code": "UNSUPPORTED_FORMAT",
        "message": "不支持的文件格式",
        "status_code": 415,
        "solution": "请上传 .ply, .las, .laz, .xyz, .pcd 或 .obj 格式的文件"
    },
    "UPLOAD_INTERRUPTED": {
        "code": "UPLOAD_INTERRUPTED",
        "message": "上传中断",
        "status_code": 400,
        "solution": "请重新上传，支持断点续传"
    },
    "STORAGE_FULL": {
        "code": "STORAGE_FULL",
        "message": "存储空间不足",
        "status_code": 507,
        "solution": "请联系管理员扩容或删除旧文件"
    },
    "FILE_CORRUPTED": {
        "code": "FILE_CORRUPTED",
        "message": "文件损坏或格式错误",
        "status_code": 400,
        "solution": "请检查文件完整性后重新上传"
    }
}

# 上传错误处理实现
async def handle_upload_error(error_type: str, details: str = None):
    error_info = UPLOAD_ERROR_HANDLERS.get(error_type, {
        "code": "UNKNOWN_ERROR",
        "message": "上传失败",
        "status_code": 500,
        "solution": "请稍后重试"
    })
    
    raise FileUploadError(
        message=f"{error_info['message']}. {error_info['solution']}",
        code=error_info['code']
    )
```

### 3.2 处理超时处理

```python
# 任务超时配置
TASK_TIMEOUT_CONFIG = {
    "filter_voxel": 300,      # 5分钟
    "filter_statistical": 600,  # 10分钟
    "segment_ransac": 900,    # 15分钟
    "register_icp": 1800,     # 30分钟
    "ai_detection": 3600      # 1小时
}

# 超时处理
async def handle_task_timeout(task_id: int, task_type: str):
    timeout = TASK_TIMEOUT_CONFIG.get(task_type, 600)
    
    # 更新任务状态
    await update_task_status(
        task_id=task_id,
        status="failed",
        error_message=f"任务处理超时（超过{timeout}秒）",
        error_code="TASK_TIMEOUT"
    )
    
    # 发送通知
    await send_notification(
        user_id=task.user_id,
        title="任务处理超时",
        message=f"您的{task_type}任务因处理时间过长而失败，请尝试减小数据量或降低精度"
    )
```

### 3.3 数据库错误处理

```python
# 数据库错误重试机制
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((OperationalError, TimeoutError))
)
async def execute_with_retry(db_session, query):
    """带重试的数据库执行"""
    try:
        result = await db_session.execute(query)
        return result
    except OperationalError as e:
        logger.warning(f"Database operation failed, retrying... {e}")
        raise

# 连接池监控
async def monitor_db_connection_pool():
    """监控数据库连接池"""
    pool = engine.pool
    
    stats = {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow()
    }
    
    # 如果连接池耗尽，发送告警
    if stats["overflow"] > 10:
        logger.error(f"Database connection pool exhausted: {stats}")
        await send_alert("Database pool exhaustion", stats)
```

## 4. 前端错误处理

### 4.1 错误拦截器

```typescript
// frontend/src/services/api.ts
import axios from 'axios'
import { ElMessage, ElNotification } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

// 错误码映射
const ERROR_MESSAGES: Record<string, string> = {
  'AUTH_ERROR': '认证失败，请重新登录',
  'FORBIDDEN': '权限不足',
  'NOT_FOUND': '请求的资源不存在',
  'VALIDATION_ERROR': '输入参数有误',
  'UPLOAD_ERROR': '文件上传失败',
  'PROCESSING_ERROR': '处理失败',
  'TIMEOUT_ERROR': '请求超时',
  'FILE_TOO_LARGE': '文件过大',
  'UNSUPPORTED_FORMAT': '不支持的文件格式',
  'STORAGE_FULL': '存储空间不足',
  'TASK_TIMEOUT': '任务处理超时'
}

// 响应拦截器
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const { response } = error
    
    if (response) {
      const { status, data } = response
      const errorCode = data?.error?.code
      const errorMessage = ERROR_MESSAGES[errorCode] || data?.message || '请求失败'
      
      switch (status) {
        case 401:
          // 认证失败，清除token并跳转登录
          const authStore = useAuthStore()
          authStore.clearAuth()
          ElMessage.error('登录已过期，请重新登录')
          window.location.href = '/login'
          break
          
        case 403:
          ElNotification.error({
            title: '权限不足',
            message: '您没有执行此操作的权限'
          })
          break
          
        case 404:
          ElMessage.error('请求的资源不存在')
          break
          
        case 413:
          ElMessage.error('文件过大，请分批上传')
          break
          
        case 422:
          // 验证错误，显示详细信息
          const details = data?.error?.details
          if (Array.isArray(details)) {
            details.forEach((err: any) => {
              ElMessage.error(`${err.field}: ${err.message}`)
            })
          } else {
            ElMessage.error(errorMessage)
          }
          break
          
        case 500:
        case 502:
        case 503:
        case 504:
          ElNotification.error({
            title: '服务器错误',
            message: errorMessage
          })
          break
          
        default:
          ElMessage.error(errorMessage)
      }
    } else {
      // 网络错误
      if (error.code === 'ECONNABORTED') {
        ElMessage.error('请求超时，请稍后重试')
      } else {
        ElMessage.error('网络错误，请检查网络连接')
      }
    }
    
    return Promise.reject(error)
  }
)

export default api
```

### 4.2 全局错误边界

```vue
<!-- frontend/src/components/ErrorBoundary.vue -->
<template>
  <div v-if="hasError" class="error-boundary">
    <el-result
      icon="error"
      title="出错了"
      :sub-title="errorMessage"
    >
      <template #extra>
        <el-button type="primary" @click="reload">重新加载</el-button>
        <el-button @click="goHome">返回首页</el-button>
      </template>
    </el-result>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((error, instance, info) => {
  hasError.value = true
  errorMessage.value = error.message || '发生未知错误'
  
  // 上报错误
  console.error('Error captured:', error, instance, info)
  
  return false
})

const reload = () => {
  window.location.reload()
}

const goHome = () => {
  router.push('/')
  hasError.value = false
}
</script>
```

## 5. 监控与告警

### 5.1 错误日志

```python
# 日志配置
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "json": {
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json"
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/error.log",
            "maxBytes": 10485760,
            "backupCount": 10,
            "formatter": "json",
            "level": "ERROR"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file", "error_file"]
    }
}
```

### 5.2 错误告警

```python
# 告警配置
ALERT_CONFIG = {
    "webhook_url": "https://hooks.slack.com/services/xxx",
    "email_recipients": ["admin@example.com"],
    "thresholds": {
        "error_rate": 0.05,  # 5%错误率告警
        "response_time": 5000,  # 5秒响应时间告警
        "concurrent_users": 100  # 并发用户数告警
    }
}

async def send_alert(title: str, details: dict):
    """发送告警"""
    import aiohttp
    
    payload = {
        "text": f"🚨 {title}",
        "attachments": [{
            "color": "danger",
            "fields": [
                {"title": k, "value": str(v), "short": True}
                for k, v in details.items()
            ]
        }]
    }
    
    async with aiohttp.ClientSession() as session:
        await session.post(ALERT_CONFIG["webhook_url"], json=payload)
```

## 6. 用户友好的错误提示

### 6.1 错误提示原则

1. **清晰明确**：告诉用户发生了什么
2. **提供解决方案**：告诉用户如何解决问题
3. **避免技术术语**：使用用户能理解的语言
4. **提供支持渠道**：在无法解决时提供帮助

### 6.2 错误提示示例

| 错误场景 | 错误提示 | 解决方案 |
|---------|---------|---------|
| 文件过大 | "文件大小超过500MB限制" | "请压缩文件或分批上传" |
| 格式不支持 | "不支持的文件格式" | "请上传PLY、LAS、XYZ等格式" |
| 处理超时 | "处理时间过长" | "请减小数据量或降低精度" |
| 存储不足 | "存储空间不足" | "请删除旧文件或联系管理员" |
| 网络错误 | "网络连接失败" | "请检查网络后重试" |
| 权限不足 | "无权执行此操作" | "请联系场景所有者获取权限" |
