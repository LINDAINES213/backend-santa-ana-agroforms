FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app


RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates apt-transport-https \
      unixodbc unixodbc-dev libgssapi-krb5-2; \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg; \
    curl -fsSL https://packages.microsoft.com/config/debian/11/prod.list \
      -o /etc/apt/sources.list.d/mssql-release.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
      msodbcsql17 mssql-tools; \
    ln -s /opt/mssql-tools/bin/sqlcmd /usr/local/bin/sqlcmd || true; \
    ln -s /opt/mssql-tools/bin/bcp /usr/local/bin/bcp || true; \
    # Diagnóstico (no rompe): ver qué detecta odbcinst
    (odbcinst -q -d || true); \
    # 2) Verificación dura por presencia de librerías del driver 17
    if ls /opt/microsoft/msodbcsql17/lib64/libmsodbcsql-17*.so* >/dev/null 2>&1; then \
      echo "msodbcsql17 OK"; \
    else \
      echo "FALTA msodbcsql17 (no se encontró libmsodbcsql-17*.so)"; \
      exit 1; \
    fi; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . /app/


EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
