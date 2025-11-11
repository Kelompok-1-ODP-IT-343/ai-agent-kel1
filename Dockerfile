# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

# --- Environment setup ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=on

WORKDIR /app

# --- Install dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- Copy source code ---
COPY data ./data
COPY . .

# --- Set environment variables ---
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=9090
EXPOSE 9090

# --- Run Flask directly ---
CMD ["flask", "run"]
