import aiohttp
from config import BACKEND_INTERNAL_URL


class ApiClient:
    """Обёртка над backend REST API для клиентского сценария VK-бота.

    Backend работает по заголовкам platform/user-id; этот клиент передаёт
    platform="vk" и покрывает используемые ботом методы.
    """

    def __init__(self, user_id: str):
        self.base_url = BACKEND_INTERNAL_URL.rstrip("/")
        self.user_id = user_id

    def _headers(self):
        return {"platform": "vk", "user-id": self.user_id}

    async def register(self, first_name=None, last_name=None, username=None, phone=None):
        params = {}
        if first_name: params["first_name"] = first_name
        if last_name: params["last_name"] = last_name
        if username: params["username"] = username
        if phone: params["phone"] = phone
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/users/register",
                headers=self._headers(), params=params
            ) as resp:
                return await resp.json()

    async def get_me(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/clients/me", headers=self._headers()
            ) as resp:
                return await resp.json()

    async def get_services(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/services", headers=self._headers()
            ) as resp:
                return await resp.json()

    async def get_my_cars(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/cars", headers=self._headers()
            ) as resp:
                return await resp.json()

    async def add_car(self, brand, model):
        params = {"brand": brand, "model": model}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/cars", headers=self._headers(), params=params
            ) as resp:
                return await resp.json()

    async def get_schedule(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/schedule", headers=self._headers()
            ) as resp:
                return await resp.json()

    async def get_busy_slots(self, date_str: str, service_id: int = None):
        params = {"date": date_str}
        if service_id is not None:
            params["service_id"] = service_id
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/appointments/slots",
                headers=self._headers(), params=params
            ) as resp:
                return await resp.json()

    async def create_appointment(self, car_id, service_id, start_datetime, phone=None):
        params = {"car_id": car_id, "service_id": service_id, "start_datetime": start_datetime}
        if phone:
            params["phone"] = phone
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/appointments",
                headers=self._headers(), params=params
            ) as resp:
                data = await resp.json()
                return resp.status, data

    async def get_my_appointments(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/appointments/my", headers=self._headers()
            ) as resp:
                return await resp.json()

    async def cancel_appointment(self, appointment_id: int):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/appointments/{appointment_id}/cancel",
                headers=self._headers()
            ) as resp:
                data = await resp.json()
                return resp.status, data

    async def get_my_works(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/works/my", headers=self._headers()
            ) as resp:
                return await resp.json()

    async def update_profile(self, name: str = None, phone: str = None):
        params = {}
        if name is not None:
            params["name"] = name
        if phone is not None:
            params["phone"] = phone
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                f"{self.base_url}/api/v1/clients/me",
                headers=self._headers(), params=params
            ) as resp:
                return await resp.json()

    async def get_contacts(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/contacts", headers=self._headers()
            ) as resp:
                return await resp.json()
