FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

# Dependencias mínimas (PostgreSQL runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 build-essential curl ca-certificates \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -m pip show gunicorn \
 && python -m gunicorn --version

COPY . .

# Si usas collectstatic
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Nota: usar python -m gunicorn evita problemas de PATH
CMD exec python -m gunicorn backend.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 3 --threads 2 --timeout 120