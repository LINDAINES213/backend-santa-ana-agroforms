FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar unixODBC y driver 17 de SQL Server
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates apt-transport-https \
      unixodbc unixodbc-dev \
      libgssapi-krb5-2 \
    && curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/config/debian/${VERSION_ID}/prod.list" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 mssql-tools \
    && ln -s /opt/mssql-tools/bin/sqlcmd /usr/local/bin/sqlcmd || true \
    && ln -s /opt/mssql-tools/bin/bcp /usr/local/bin/bcp || true \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
