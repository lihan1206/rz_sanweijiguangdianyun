from functools import lru_cache
from pathlib import Path

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

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    upload_dir: str = "/app/uploads"
    log_dir: str = "/app/logs"
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    task_timeout: int = 600  # 10分钟

    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/0"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def log_path(self) -> Path:
        return Path(self.log_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
