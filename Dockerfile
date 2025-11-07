# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=on \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# (opsional) sistem paket untuk lib native
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# deps dulu supaya cache efektif
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# salin source
COPY . .

# port default API
ENV PORT=8000
EXPOSE 8000

# ---- ENTRYPOINT ----
# Jika project kamu FastAPI dengan file app.py berisi variable "app"
# ganti sesuai struktur kamu (misal "src.main:app")
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8000"]

# Jika Flask:
# CMD ["python","app.py"]
