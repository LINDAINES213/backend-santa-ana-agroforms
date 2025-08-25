# Imagen base oficial de Python
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

# Paquetes de sistema necesarios (ODBC y utilidades)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates apt-transport-https \
    unixodbc unixodbc-dev libgssapi-krb5-2 build-essential \
 && mkdir -p /usr/share/keyrings \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg arch=amd64] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/microsoft.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
      msodbcsql17 mssql-tools18 \
 && ln -s /opt/mssql-tools18/bin/sqlcmd /usr/local/bin/sqlcmd \
 && ln -s /opt/mssql-tools18/bin/bcp /usr/local/bin/bcp \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto
COPY . .

# Collectstatic (asegúrate de tener STATIC_ROOT en settings.py)
RUN python manage.py collectstatic --noinput || true

# Exponer puerto (Koyeb usará $PORT, pero lo declaramos para local)
EXPOSE 8000

# CMD con gunicorn (más estable que runserver en producción)
CMD exec gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --threads 2 --timeout 120
