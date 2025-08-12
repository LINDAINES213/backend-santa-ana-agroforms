# Imagen base oficial de Python (Debian slim)
FROM python:3.11-slim

# Configuración recomendada de Python en contenedores
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# 1) Instalar unixODBC y ODBC Driver 17 para SQL Server
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates apt-transport-https \
      unixodbc unixodbc-dev libgssapi-krb5-2 \
    && curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/config/debian/${VERSION_ID}/prod.list" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 mssql-tools \
    && ln -s /opt/mssql-tools/bin/sqlcmd /usr/local/bin/sqlcmd || true \
    && ln -s /opt/mssql-tools/bin/bcp /usr/local/bin/bcp || true \
    && rm -rf /var/lib/apt/lists/*

# 2) Instalar dependencias de Python
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 3) Copiar el código del proyecto
COPY . /app/

# Exponer puerto
EXPOSE 8000

# Comando por defecto (modo desarrollo)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]