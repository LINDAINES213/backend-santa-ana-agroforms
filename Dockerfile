# Imagen base oficial de Python
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

# Paquetes del sistema mínimos para Django + PostgreSQL
# - libpq5: runtime de PostgreSQL
# - build-essential (opcional si compilas extensiones nativas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 build-essential curl ca-certificates \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias de Python
# Recomendado: usar psycopg 3 binario para evitar compilar
# (en tu requirements.txt incluye: psycopg[binary]==3.2.3 por ejemplo)
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto
COPY . .

# Collectstatic (no falla si no tienes static configurado)
RUN python manage.py collectstatic --noinput || true

# Exponer puerto
EXPOSE 8000

# Arranque con gunicorn (producción)
CMD exec gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --threads 2 --timeout 120