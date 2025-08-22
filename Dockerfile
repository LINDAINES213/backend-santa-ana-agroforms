# Imagen base oficial de Python
FROM python:3.11.8-slim-bookworm

# Update system packages to reduce vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get dist-upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar archivos del proyecto
COPY . /app/

# Instalar dependencias
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Exponer puerto
EXPOSE 8000

# Ejecutar servidor de desarrollo (puedes cambiar a gunicorn si quieres producción)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]