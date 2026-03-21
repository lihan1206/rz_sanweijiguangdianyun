# 错误处理方案

## 1. 文件上传错误处理

### 1.1 文件格式不支持
- **错误代码**: 400 Bad Request
- **场景**: 用户上传了不支持的点云格式
- **处理方式**:
  - 后端验证文件扩展名，返回支持的格式列表
  - 前端在上传前进行格式预校验
- **示例响应**:
```json
{
  "detail": "不支持的点云格式: abc，当前支持 las, laz, ply, xyz, e57, csv"
}
```

### 1.2 文件大小超限
- **错误代码**: 413 Payload Too Large
- **场景**: 上传文件超过服务器限制
- **处理方式**:
  - Nginx配置 `client_max_body_size` 限制
  - FastAPI 使用 `UploadFile` 流式处理大文件
  - 分片上传支持超大文件（>100MB）
- **解决方案**:
```python
# 分片上传实现
@router.post("/upload/chunk")
async def upload_chunk(
    file: UploadFile,
    chunk_index: int,
    total_chunks: int,
    upload_id: str,
):
    # 合并分片逻辑
    pass
```

### 1.3 文件损坏或格式错误
- **错误代码**: 422 Unprocessable Entity
- **场景**: 文件内容损坏或格式不符合规范
- **处理方式**:
  - 解析文件时捕获异常
  - 记录详细错误日志
  - 返回具体错误位置信息

## 2. 点云处理错误处理

### 2.1 处理超时
- **错误代码**: 408 Request Timeout
- **场景**: 点云处理任务执行时间过长
- **处理方式**:
  - 设置任务超时时间（默认30分钟）
  - 使用 Celery 或后台任务队列
  - 超时后自动标记任务失败
```python
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("处理超时")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(1800)  # 30分钟超时
try:
    process_pointcloud()
finally:
    signal.alarm(0)
```

### 2.2 内存不足
- **错误代码**: 503 Service Unavailable
- **场景**: 处理大点云时内存耗尽
- **处理方式**:
  - 分块处理大文件
  - 使用生成器减少内存占用
  - 设置内存监控，超过阈值拒绝新任务
```python
def process_large_pointcloud(file_path: str, chunk_size: int = 100000):
    points = []
    for chunk in read_chunks(file_path, chunk_size):
        processed_chunk = process_chunk(chunk)
        points.extend(processed_chunk)
        yield processed_chunk
```

### 2.3 处理算法失败
- **错误代码**: 500 Internal Server Error
- **场景**: 算法执行过程中出现异常
- **处理方式**:
  - 捕获所有异常并记录
  - 更新任务状态为 FAILED
  - 保存错误信息到数据库
```python
try:
    result = run_advanced_processing(points, task_type, params)
except ValueError as e:
    task.status = TaskStatus.FAILED
    task.error_message = f"参数错误: {str(e)}"
except Exception as e:
    task.status = TaskStatus.FAILED
    task.error_message = f"处理失败: {str(e)}"
    logger.exception("任务执行失败")
finally:
    db.commit()
```

## 3. WebSocket 连接错误处理

### 3.1 连接断开
- **场景**: WebSocket 连接意外断开
- **处理方式**:
  - 客户端自动重连机制
  - 服务端清理会话状态
  - 通知其他用户
```typescript
// 前端重连逻辑
const connectWebSocket = (token: string, sceneId: number) => {
  const ws = new WebSocket(wsUrl);
  
  ws.onclose = () => {
    setTimeout(() => {
      connectWebSocket(token, sceneId);
    }, 3000); // 3秒后重连
  };
};
```

### 3.2 认证失败
- **错误代码**: 4004 (WebSocket Close Code)
- **场景**: session_token 无效或过期
- **处理方式**:
  - 关闭 WebSocket 连接
  - 提示用户重新加入场景

### 3.3 消息格式错误
- **场景**: 接收到无效的 JSON 消息
- **处理方式**:
  - 忽略无效消息
  - 返回错误提示
```python
try:
    message = json.loads(data)
except json.JSONDecodeError:
    await websocket.send_json({"error": "无效的JSON格式"})
    return
```

## 4. 数据库错误处理

### 4.1 连接失败
- **错误代码**: 503 Service Unavailable
- **场景**: 数据库连接池耗尽或数据库不可用
- **处理方式**:
  - 配置连接池参数
  - 实现重试机制
  - 返回服务不可用提示
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
)
```

### 4.2 并发冲突
- **错误代码**: 409 Conflict
- **场景**: 多用户同时修改同一数据
- **处理方式**:
  - 使用乐观锁（版本号）
  - 悲观锁（SELECT FOR UPDATE）
  - 返回冲突提示

### 4.3 外键约束错误
- **错误代码**: 400 Bad Request
- **场景**: 引用不存在的数据
- **处理方式**:
  - 操作前验证关联数据存在
  - 返回具体错误信息

## 5. 认证授权错误处理

### 5.1 Token 过期
- **错误代码**: 401 Unauthorized
- **场景**: JWT Token 已过期
- **处理方式**:
  - 前端自动刷新 Token
  - 跳转登录页面
```typescript
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      clearAuth();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### 5.2 权限不足
- **错误代码**: 403 Forbidden
- **场景**: 用户角色无权执行操作
- **处理方式**:
  - 返回权限不足提示
  - 隐藏无权限的功能按钮

### 5.3 恶意文件上传
- **错误代码**: 400 Bad Request
- **场景**: 检测到恶意文件
- **处理方式**:
  - 文件类型验证（魔数检测）
  - 文件内容扫描
  - 记录安全日志
```python
MAGIC_NUMBERS = {
    b'ply': 'ply',
    b'\x00\x00\x00\x00': 'las',
}

def validate_file_type(file_path: str) -> str | None:
    with open(file_path, 'rb') as f:
        header = f.read(4)
    for magic, file_type in MAGIC_NUMBERS.items():
        if header.startswith(magic):
            return file_type
    return None
```

## 6. 系统级错误处理

### 6.1 服务启动失败
- **场景**: 依赖服务（数据库）未就绪
- **处理方式**:
  - Docker healthcheck 等待依赖
  - 启动时重试连接
```yaml
healthcheck:
  test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
  interval: 10s
  timeout: 5s
  retries: 10
```

### 6.2 磁盘空间不足
- **错误代码**: 507 Insufficient Storage
- **场景**: 上传目录磁盘空间不足
- **处理方式**:
  - 定期清理临时文件
  - 监控磁盘使用率
  - 设置存储配额

### 6.3 服务过载
- **错误代码**: 429 Too Many Requests
- **场景**: 请求频率超过限制
- **处理方式**:
  - 实现请求限流
  - 返回重试时间
```python
from fastapi import Request
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@app.post("/upload")
@limiter.limit("10/minute")
async def upload(request: Request):
    pass
```

## 7. 错误日志与监控

### 7.1 日志记录
- 所有错误记录到日志文件
- 包含请求ID、用户ID、错误堆栈
- 日志级别：DEBUG、INFO、WARNING、ERROR、CRITICAL

### 7.2 告警机制
- 错误率超过阈值触发告警
- 关键服务不可用立即告警
- 支持邮件、短信、Webhook 通知

### 7.3 错误追踪
- 使用 Sentry 等工具追踪错误
- 关联用户操作上下文
- 支持错误重现
