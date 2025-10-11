# Santa Ana AgroForms Backend (Django REST)

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Django](https://img.shields.io/badge/Django-5.x-0C4B33)
![DRF](https://img.shields.io/badge/DRF-3.16-red)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED)

> Backend para la plataforma web **Santa Ana AgroForms**: creación, edición y gestión de formularios consumidos por una app móvil (con soporte offline). Incluye otras funciones como exportación de respuestas, creación de usuarios, accesos, asignaciones de formularios, uso de datasets externos (Excel), autenticación OAuth2 y documentación OpenAPI.

---

## ✨ Características clave

* **Gestión de Formularios**:
  * Acciones: crear formularios, páginas, campos, duplicación, edición y eliminación de formularios.
* **Campos avanzados**:
  * **Campos de Tipo Grupo** que agrupa campos dentro de ellos.
  * **Fuentes de Datos** para autocompletar campos desde data de un Excel.
* **Asignaciones**: asigna formularios a usuarios (multiselección) y controla su disponibilidad.
* **Exportaciones**: descarga de respuestas en **Excel**.
* **Autenticación**: OAuth2 (django-oauth-toolkit).
* **Documentación**: Swagger UI / Redoc servidos desde el backend (`drf-spectacular`).
---

## 🧱 Stack

* **Python 3.11**, **Django 5.x**, **Django REST Framework 3.16**
* **drf-spectacular** para OpenAPI 3
* **django-oauth-toolkit** para OAuth2
* **Azure Blob Storage** (SDK oficial) para datasets Excel
* **PostgreSQL** como base de datos

---

## 📚 Endpoints principales

* `POST /api/formularios/` → creación de un formulario.
* `POST /api/formularios/{id}/duplicar/` → duplica un formulario específico completo.
* `POST /api/formularios/{id}/agregar-pagina/` → crea una página en un formulario en específico.
* `POST /api/paginas/{id}/campos/` → agrega campo en una página en específico.
* `GET /api/asignaciones/` y `POST /api/asignaciones/crear-asignacion/` → asignaciones de ciertos formularios a los usuarios registrados.
* `POST /api/fuentes-datos` → permite subir archivos de Excel para su uso posterior en campos de autocompletado.
* `POST /api/auth/login` → Ruta para hacer login y obtener acceso a las rutas
* **Docs**: `/api/schema/doc/`.

---

## 🚀 Quickstart

## 🔧 Configuración (.env)

Variables necesarias para correr la API, reemplazar los valores a la derecha por los reales:

```dotenv
DATABASE_HOST=HOST
DATABASE_USER=USER
DATABASE_PASSWORD=PASSWORD
DATABASE_NAME=DB

AZURE_STORAGE_CONNECTION_STRING=STRING
AZURE_CONTAINER=CONTAINER
AZURE_ACCOUNT_NAME=ACCOUNT
AZURE_ACCOUNT_KEY=KEY
```

## 🐳 Imagen desde Docker Hub

Como primer paso se debe tener descargado e instalado Docker Desktop. Luego de tenerlo listo ejecutar los siguientes comandos desde PowerShell:

```bash
docker pull lindain1333/santa-ana-api
```

```bash
docker run -d `
  --name agroforms-api `
  --env-file "${pwd}\.env" `
  -p 8082:8082 `
  lindain1333/santa-ana-api:latest `
  python manage.py runserver 0.0.0.0:8082
```
> Si se usa el puerto 8082 visualizar la API en `http://localhost:8082/api/docs`, sino reemplazar por el puerto que se coloque

> Nota: Tomar en cuenta que se debe ejecutar dentro de la carpeta que se encuentre las credencuales en el archivo .env

---

## 💻 Desarrollo local (sin Docker)

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

python manage.py runserver 8081
```

Visita: `http://localhost:8081/api/docs`

---

## 🚀 API Desplegada

Visita: `https://santa-ana-api.onrender.com/api/docs`. Considerar que se debe usar la ruta de autenticación login con usuario y contraseña, y el access_token devuelto introducirse en la sección de BearerAuth para que se pueda tener acceso al uso de rutas.

---

## 🔗 Docker Hub

La imagen oficial se publica en: `https://hub.docker.com/r/lindain1333/santa-ana-api`

---

## 👩🏽‍💻 Autor

* Linda Jiménez `https://github.com/LINDAINES213`
