@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: .env file not found in project root.
    echo Copy .env.example to .env and fill it in, then run this script again.
    pause
    exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
    echo ERROR: Docker not found. Install Docker Desktop:
    echo https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

echo Starting Service Company (Docker Compose)...
docker compose up -d --build --wait
if errorlevel 1 (
    echo ERROR: "docker compose up --wait" failed, see the output above.
    pause
    exit /b 1
)

echo.
echo Done! Everything is running.
echo    Backend / Swagger: http://localhost:8000/docs
echo    VK bot: write to the community.
echo    Web admin: http://localhost:8000/admin
echo.
echo Bot logs below (Ctrl+C exits the logs; containers keep running in the background).
echo Stop everything with:  docker compose down
echo.
docker compose logs -f vk_bot
