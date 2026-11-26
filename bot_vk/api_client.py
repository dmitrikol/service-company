import asyncio
import hashlib
import hmac
import json
import logging

import aiohttp

from config import BACKEND_INTERNAL_URL, HMAC_SECRET

log = logging.getLogger("vk_bot.api_client")

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)
BACKEND_UNAVAILABLE = {"detail": "backend недоступен"}
TOKEN_VERSION = "v1"


class ApiClient:
    """Обёртка над backend REST API для клиентского сценария VK-бота.

    Backend работает по заголовкам platform/user-id; этот клиент передаёт
    platform="vk" и подписывает запросы заголовком x-client-token. Все запросы
    имеют таймаут, а не-успешные HTTP-статусы пишутся в лог.
    """

    def __init__(self, user_id: str):
        self.base_url = BACKEND_INTERNAL_URL.rstrip("/")
        self.user_id = user_id
        if not HMAC_SECRET:
            log.error("HMAC_SECRET не задан: backend отклонит запросы бота (401)")

    def _client_token(self) -> str:
        """Подпись (platform, user-id) тем же алгоритмом, что и в backend."""
        message = f"{TOKEN_VERSION}:vk:{self.user_id}".encode("utf-8")
        return hmac.new(HMAC_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def _headers(self):
        return {
            "platform": "vk",
            "user-id": self.user_id,
            "x-client-token": self._client_token(),
        }

    async def _request(self, method: str, path: str, params: dict | None = None):
        """Возвращает (http_status, json_body) даже при сетевой ошибке."""
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.request(
                    method,
                    self.base_url + path,
                    headers=self._headers(),
                    params=params,
                ) as resp:
                    raw = await resp.text()
                    try:
                        data = json.loads(raw) if raw else {}
                    except (ValueError, TypeError):
                        data = {"detail": "некорректный ответ backend"}
                    if not 200 <= resp.status < 300:
                        log.warning(
                            "backend %s %s вернул HTTP %s", method, path, resp.status
                        )
                    return resp.status, data
        except (aiohttp.ClientError, asyncio.TimeoutError):
            log.warning("backend %s %s недоступен или не ответил вовремя", method, path)
            return 0, dict(BACKEND_UNAVAILABLE)

    async def _data(self, method: str, path: str, params: dict | None = None):
        """Для методов, где вызываему важен только результат (список/словарь)."""
        _, data = await self._request(method, path, params)
        return data

    async def register(self, first_name=None, last_name=None, username=None, phone=None):
        params = {}
        if first_name: params["first_name"] = first_name
        if last_name: params["last_name"] = last_name
        if username: params["username"] = username
        if phone: params["phone"] = phone
        return await self._data("POST", "/api/v1/users/register", params)

    async def get_me(self):
        return await self._data("GET", "/api/v1/clients/me")

    async def get_services(self):
        return await self._data("GET", "/api/v1/services")

    async def get_my_cars(self):
        return await self._data("GET", "/api/v1/cars")

    async def add_car(self, brand, model):
        return await self._data("POST", "/api/v1/cars", {"brand": brand, "model": model})

    async def get_schedule(self):
        return await self._data("GET", "/api/v1/schedule")

    async def get_busy_slots(self, date_str: str, service_id: int = None):
        params = {"date": date_str}
        if service_id is not None:
            params["service_id"] = service_id
        return await self._data("GET", "/api/v1/appointments/slots", params)

    async def create_appointment(self, car_id, service_id, start_datetime, phone=None):
        params = {"car_id": car_id, "service_id": service_id, "start_datetime": start_datetime}
        if phone:
            params["phone"] = phone
        return await self._request("POST", "/api/v1/appointments", params)

    async def get_my_appointments(self):
        return await self._data("GET", "/api/v1/appointments/my")

    async def cancel_appointment(self, appointment_id: int):
        return await self._request(
            "POST", f"/api/v1/appointments/{appointment_id}/cancel"
        )

    async def get_my_works(self):
        return await self._data("GET", "/api/v1/works/my")

    async def update_profile(self, name: str = None, phone: str = None):
        params = {}
        if name is not None:
            params["name"] = name
        if phone is not None:
            params["phone"] = phone
        return await self._data("PATCH", "/api/v1/clients/me", params)

    async def get_contacts(self):
        return await self._data("GET", "/api/v1/contacts")
