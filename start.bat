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

echo Starting Vmatiy Element (Docker Compose)...
docker compose up -d --build
if errorlevel 1 (
    echo ERROR: "docker compose up" failed, see the output above.
    pause
    exit /b 1
)

echo Waiting for the database...
set COUNT=0

:wait_loop
docker compose exec -T postgres pg_isready -U autoservice >nul 2>nul
if %errorlevel% equ 0 goto db_ready
set /a COUNT+=1
if %COUNT% geq 30 goto db_ready
ping -n 2 127.0.0.1 >nul
goto wait_loop

:db_ready
echo Applying database migrations...
docker compose exec -T backend alembic upgrade head

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
