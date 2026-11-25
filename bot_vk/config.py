"""Конфигурация VK-бота — читается из переменных окружения (.env через docker-compose)."""
import os

VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID") or "0")
BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")

# VK--id администратора, которому бот шлёт уведомления о записях/отменах.
# Можно указать id пользователя (положительный) или id беседы (отрицательный).
ADMIN_VK_ID = int(os.getenv("ADMIN_VK_ID") or "0")
