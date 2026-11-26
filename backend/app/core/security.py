"""Подпись клиентских запросов к backend.

Клиентские эндпоинты определяют пользователя по заголовкам ``platform`` и
``user-id``. Без подписи любой желающий мог подставить чужой id. Боты знают
общий ``HMAC_SECRET`` и добавляют заголовок ``x-client-token``; backend
проверяет его до обращения к БД.
"""
import hashlib
import hmac

from fastapi import Header, HTTPException

from app.core.config import settings

TOKEN_VERSION = "v1"


def client_token(platform: str, user_id: str, secret: str | None = None) -> str:
    """Детерминированная подпись пары (platform, user-id)."""
    key = (secret if secret is not None else settings.HMAC_SECRET).encode("utf-8")
    message = f"{TOKEN_VERSION}:{platform}:{user_id}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


async def require_client(
    platform: str = Header(...),
    user_id: str = Header(...),
    token: str | None = Header(None, alias="x-client-token"),
) -> None:
    """Пропускает запрос, только если подпись соответствует заголовкам."""
    expected = client_token(platform, user_id)
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid client token")
