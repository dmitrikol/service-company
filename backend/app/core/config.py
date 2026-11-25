from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    REDIS_URL: str
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_NAME: str
    ENCRYPTION_KEY: str
    HMAC_SECRET: str
    BACKEND_INTERNAL_URL: str = "http://backend:8000"
    VK_GROUP_TOKEN: str
    VK_GROUP_ID: int
    ADMIN_VK_ID: int = 0

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()