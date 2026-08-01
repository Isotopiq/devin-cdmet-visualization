from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/metabolomics"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    UPLOAD_DIR: str = "uploads"
    FRONTEND_URL: Optional[str] = None
    RESET_TOKEN_IN_RESPONSE: bool = False
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    S3_ENABLED: bool = False
    S3_ENDPOINT_URL: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_REGION: Optional[str] = None
    S3_USE_PATH_STYLE: bool = False


settings = Settings()
