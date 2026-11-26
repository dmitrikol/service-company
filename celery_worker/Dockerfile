FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple/
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt
COPY . .
# --beat включает встроенный планировщик (beat_schedule из tasks.py)
CMD ["celery", "-A", "tasks", "worker", "--beat", "--loglevel=info"]