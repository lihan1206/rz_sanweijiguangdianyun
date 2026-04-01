from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # 数据库配置
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "pointcloud_db"
    db_user: str = "pointcloud_user"
    db_password: str = "pointcloud_pass"
    database_url: Optional[str] = None
    
    # JWT 配置
    secret_key: str = "your-super-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # 文件上传配置
    max_file_size: int = 52428800  # 50MB
    upload_timeout: int = 300  # 5分钟
    upload_dir: str = "./uploads"
    processed_dir: str = "./processed"
    
    # 日志配置
    log_level: str = "INFO"
    log_dir: str = "./logs"
    
    # 点云处理配置
    max_points_per_file: int = 10000000
    processing_timeout: int = 600  # 10分钟
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.database_url:
            self.database_url = (
                f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
