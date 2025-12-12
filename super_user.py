import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

# AHORA sí puedes importar modelos
from formularios.models import Usuario

# Crear superusuario
Usuario.objects.create_superuser(
    nombre_usuario='TU-NOMBRE-USUARIO',
    nombre='TU-NOMBRE',
    correo='TU-CORREO',
    password='TU-PASSWORD',
    activo=True,
    acceso_web=True
)
print("✓ Superusuario creado exitosamente")
