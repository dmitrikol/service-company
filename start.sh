#!/usr/bin/env bash
# Запуск бота «Service Company» одной командой: ./start.sh
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "❌ Не найден .env в корне проекта."
    echo "   Скопируйте .env.example в .env и заполните его (см. README.md), затем запустите снова."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ Docker не найден. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
fi

echo "🚀 Запускаю Service Company (Docker Compose)..."
docker compose up -d --build

echo "⏳ Жду базу данных..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U autoservice > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "🗄  Применяю миграции..."
docker compose exec -T backend alembic upgrade head

echo ""
echo "✅ Всё запущено!"
echo "   Backend / Swagger: http://localhost:8000/docs"
echo "   VK-бот: напишите в сообщество."
echo "   Веб-админка: http://localhost:8000/admin"
echo ""
echo "📋 Логи VK-бота (Ctrl+C — выйти из логов; контейнеры продолжат работать в фоне)."
echo "   Остановить всё:  docker compose down"
echo ""
docker compose logs -f vk_bot
