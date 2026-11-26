from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.api.v1.router import api_router

app = FastAPI()

# Подключаем роутер API
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
def admin_ui():
    """Веб-админка «Service Company» поверх существующих admin API."""
    path = Path(__file__).parent / "web" / "admin.html"
    return path.read_text(encoding="utf-8")
