from collections.abc import Generator
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.mysql_pool_size,
    max_overflow=settings.mysql_max_overflow,
    pool_recycle=settings.mysql_pool_recycle,
    echo=settings.app_env == "development",
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error("数据库会话异常: %s", str(e))
        db.rollback()
        raise
    finally:
        db.close()
