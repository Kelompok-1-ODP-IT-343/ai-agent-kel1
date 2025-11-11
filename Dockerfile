# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=on \
    POETRY_VIRTUALENVS_CREATE=false
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- penting: pastikan DB ikut ke image ---
COPY data ./data

# salin source
COPY . .

ENV PORT=8000
EXPOSE 8000

## Sesuaikan modul FastAPI kamu (umum: app.main:app) 
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
