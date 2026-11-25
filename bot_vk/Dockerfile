FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple/
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]