from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки, которые реально использует backend.

    Остальные переменные из `.env` (Redis, MinIO, VK, ENCRYPTION_KEY) нужны
    другим сервисам или зарезервированы на будущее; backend их не читает.
    """

    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    HMAC_SECRET: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
