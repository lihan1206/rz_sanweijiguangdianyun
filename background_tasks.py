import os
import time
import uuid
import asyncio
import concurrent.futures
from datetime import datetime
from typing import Dict, Any, Callable
from functools import wraps
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

PROCESSING_TIMEOUT = int(os.getenv("PROCESSING_TIMEOUT", 300))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 4))

executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

class TaskTimeoutError(Exception):
    """任务超时异常"""
    pass

class TaskError(Exception):
    """任务执行异常"""
    pass

def timeout(seconds: int = PROCESSING_TIMEOUT):
    """超时装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            def monitor():
                while time.time() - start_time < seconds:
                    time.sleep(1)
                raise TaskTimeoutError(f"Task timed out after {seconds} seconds")
            
            monitor_future = executor.submit(monitor)
            
            try:
                result = func(*args, **kwargs)
                monitor_future.cancel()
                return result
            except TaskTimeoutError:
                logger.error(f"Task timed out: {func.__name__}")
                raise
            except Exception as e:
                monitor_future.cancel()
                logger.error(f"Task failed: {e}")
                raise TaskError(f"Task failed: {str(e)}")
        
        return wrapper
    return decorator

class BackgroundTaskManager:
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.executor = executor

    def generate_task_id(self) -> str:
        """生成唯一任务ID"""
        return str(uuid.uuid4())

    def submit_task(
        self,
        func: Callable,
        *args,
        task_id: str = None,
        timeout_seconds: int = PROCESSING_TIMEOUT,
        **kwargs
    ) -> str:
        """提交任务到线程池"""
        if task_id is None:
            task_id = self.generate_task_id()

        @timeout(timeout_seconds)
        def wrapped_func():
            return func(*args, **kwargs)

        future = self.executor.submit(wrapped_func)
        
        self.tasks[task_id] = {
            'future': future,
            'status': 'running',
            'start_time': datetime.utcnow(),
            'result': None,
            'error': None
        }
        
        logger.info(f"Task submitted: {task_id}")
        return task_id

    async def wait_for_task(self, task_id: str, check_interval: float = 1.0) -> Dict[str, Any]:
        """异步等待任务完成"""
        while True:
            task_info = self.get_task_status(task_id)
            if task_info['status'] in ['completed', 'failed', 'timeout']:
                return task_info
            await asyncio.sleep(check_interval)

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if task_id not in self.tasks:
            return {'status': 'not_found', 'error': 'Task not found'}

        task_info = self.tasks[task_id]
        future = task_info['future']

        if future.done():
            try:
                result = future.result()
                task_info['status'] = 'completed'
                task_info['result'] = result
                task_info['completed_at'] = datetime.utcnow()
                task_info['duration'] = (task_info['completed_at'] - task_info['start_time']).total_seconds()
                logger.info(f"Task completed: {task_id} (duration: {task_info['duration']:.2f}s)")
            except TaskTimeoutError as e:
                task_info['status'] = 'timeout'
                task_info['error'] = str(e)
                logger.warning(f"Task timeout: {task_id}")
            except Exception as e:
                task_info['status'] = 'failed'
                task_info['error'] = str(e)
                logger.error(f"Task failed: {task_id}, error: {e}")
        elif future.running():
            task_info['status'] = 'running'
            task_info['duration'] = (datetime.utcnow() - task_info['start_time']).total_seconds()
        else:
            task_info['status'] = 'pending'

        return {
            'task_id': task_id,
            'status': task_info['status'],
            'start_time': task_info['start_time'].isoformat(),
            'duration': task_info.get('duration'),
            'result': task_info.get('result'),
            'error': task_info.get('error')
        }

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.tasks:
            return False
        
        task_info = self.tasks[task_id]
        future = task_info['future']
        
        if not future.done():
            future.cancel()
            task_info['status'] = 'cancelled'
            logger.info(f"Task cancelled: {task_id}")
            return True
        return False

    def cleanup_tasks(self, max_age_hours: int = 24):
        """清理过期任务"""
        current_time = datetime.utcnow()
        expired_tasks = []
        
        for task_id, task_info in self.tasks.items():
            if 'completed_at' in task_info:
                age = current_time - task_info['completed_at']
                if age.total_seconds() > max_age_hours * 3600:
                    expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            del self.tasks[task_id]
        
        if expired_tasks:
            logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")

    def get_running_tasks(self) -> list:
        """获取所有运行中的任务"""
        running_tasks = []
        for task_id, task_info in self.tasks.items():
            if task_info['status'] == 'running' or (task_info['future'].running() and not task_info['future'].done()):
                running_tasks.append({
                    'task_id': task_id,
                    'start_time': task_info['start_time'].isoformat(),
                    'duration': (datetime.utcnow() - task_info['start_time']).total_seconds()
                })
        return running_tasks

task_manager = BackgroundTaskManager()

def get_task_manager() -> BackgroundTaskManager:
    """获取任务管理器实例"""
    return task_manager
