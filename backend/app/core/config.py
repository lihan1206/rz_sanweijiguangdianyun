from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "三维激光点云处理平台"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 120

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_db: str = "pointcloud_platform"
    mysql_user: str = "appuser"
    mysql_password: str = "app123456"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20
    mysql_pool_recycle: int = 3600

    upload_dir: str = "/app/uploads"
    max_file_size_mb: int = 500
    max_upload_timeout_seconds: int = 300
    chunk_size: int = 1024 * 1024

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_timeout: int = 300
    celery_task_soft_timeout: int = 280

    log_level: str = "INFO"
    log_file: str = "/app/logs/app.log"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
