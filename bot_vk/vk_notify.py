"""Уведомление администратора в VK о заявках/отменах из VK-бота.

Уведомления уходят напрямую через VK API от имени сообщества. Ошибки не должны
мешать созданию записи, поэтому
все сетевые сбои гасятся и пишутся в лог.
"""
import logging
import random
import urllib.parse

import aiohttp

from config import ADMIN_VK_ID, VK_GROUP_ID, VK_GROUP_TOKEN

log = logging.getLogger("vk_bot.vk_notify")

VK_API_VERSION = "5.131"


async def _send(text: str) -> None:
    if not VK_GROUP_TOKEN or not ADMIN_VK_ID:
        log.warning(
            "VK-уведомление не отправлено: VK_GROUP_TOKEN=%s ADMIN_VK_ID=%s "
            "(проверьте .env и перезапустите контейнер vk_bot)",
            "задан" if VK_GROUP_TOKEN else "ПУСТО",
            ADMIN_VK_ID or "ПУСТО (0)",
        )
        return

    params = {
        "access_token": VK_GROUP_TOKEN,
        "v": VK_API_VERSION,
        "peer_id": ADMIN_VK_ID,
        "message": text,
        "random_id": random.randint(1, 2 ** 31 - 1),
    }
    if VK_GROUP_ID:
        params["group_id"] = abs(VK_GROUP_ID)
    url = f"https://api.vk.com/method/messages.send?{urllib.parse.urlencode(params)}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                body = await resp.text()
                if resp.status != 200:
                    log.error("VK messages.send вернул HTTP %s: %s", resp.status, body)
                    return
                data = await resp.json(content_type=None)
                if "error" in data:
                    log.error("VK messages.send error: %s", data["error"])
    except Exception:
        log.exception("Не удалось отправить VK-уведомление админу")


async def notify_new_appointment(client_name: str, service: str, car: str, when: str,
                                 phone: str = "", vk_user_id: int | None = None) -> None:
    phone_line = f"\n📞 Телефон: {phone}" if phone else ""
    profile_line = f"\n🔗 https://vk.com/id{vk_user_id}" if vk_user_id else ""
    text = (
        f"🔔 НОВАЯ ЗАПИСЬ (ВКонтакте)\n"
        f"━━━━━━━━━━━━━━\n"
        f"🧑 Клиент: {client_name}\n"
        f"🔧 Услуга: {service}\n"
        f"🚘 Автомобиль: {car}\n"
        f"🕐 {when}{phone_line}{profile_line}"
    )
    await _send(text)


async def notify_cancelled(client_name: str, service: str, car: str, when: str) -> None:
    text = (
        f"❌ ОТМЕНА ЗАПИСИ (ВКонтакте)\n"
        f"━━━━━━━━━━━━━━\n"
        f"🧑 Клиент: {client_name}\n"
        f"🔧 Услуга: {service}\n"
        f"🚘 Автомобиль: {car}\n"
        f"🕐 {when}"
    )
    await _send(text)
