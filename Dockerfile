FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

# Dependencias del sistema mínimas para Postgres y compilación básica
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 build-essential curl ca-certificates \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -m pip show uvicorn

# Copiar proyecto
COPY . .

# Static (opcional)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Importante: usar ASGI de Django (Django 3.0+)
# backend.asgi:application debe existir (creado por startproject)
CMD exec python -m uvicorn backend.asgi:application \
  --host 0.0.0.0 --port ${PORT:-8000} \
  --workers 3 --timeout-keep-alive 120