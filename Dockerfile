FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# unixODBC + repo Microsoft + msodbcsql17
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates apt-transport-https \
      unixodbc unixodbc-dev libgssapi-krb5-2 \
    && curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/config/debian/11/prod.list" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 mssql-tools \
    && ln -s /opt/mssql-tools/bin/sqlcmd /usr/local/bin/sqlcmd || true \
    && ln -s /opt/mssql-tools/bin/bcp /usr/local/bin/bcp || true \
    && rm -rf /var/lib/apt/lists/*

# Verificación: falla si el driver 17 no quedó registrado
RUN odbcinst -q -d -n "ODBC Driver 17 for SQL Server" >/dev/null || (echo "FALTA msodbcsql17" && exit 1)

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Proyecto
COPY . /app/

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
