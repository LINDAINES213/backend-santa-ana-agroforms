from django.db import models
import uuid

from formularios.auth_models import UsuarioManager
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

try:
    from django.db.models import JSONField  # Django 3.1+
except Exception:
    JSONField = None
# Create your models here.
class Categoria(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return self.nombre

    class Meta:
        # managed = False
        db_table = 'formularios_categoria'

class Rol(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        # managed = False
        db_table = "formularios_rol"  

# class Usuario(models.Model):
#     nombre_usuario = models.CharField(max_length=50, primary_key=True, db_column="nombre_usuario")
#     nombre = models.CharField(max_length=100)
#     correo = models.EmailField(unique=True)
#     contrasena = models.CharField(max_length=128)
#     activo = models.BooleanField(default=True)

#     roles = models.ManyToManyField(
#         "formularios.Rol",
#         through="formularios.RolUser",
#         related_name="usuarios",
#     )

#     class Meta:
#         # managed = False
#         db_table = "formularios_usuario"
#         ordering = ("nombre",)


class Usuario(AbstractBaseUser, PermissionsMixin):
    nombre_usuario = models.CharField(max_length=50, primary_key=True, db_column="nombre_usuario")
    nombre = models.CharField(max_length=100)
    correo = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    activo = models.BooleanField(default=True)
    acceso_web = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)


    roles = models.ManyToManyField(
        "Rol",
        through="RolUser",
        related_name="usuarios",
    )

    # Agregar estos campos para evitar conflictos
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='formularios_usuarios',
        related_query_name='formularios_usuario',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='formularios_usuarios',
        related_query_name='formularios_usuario',
    )

    objects = UsuarioManager()

    USERNAME_FIELD = 'nombre_usuario'
    REQUIRED_FIELDS = ['correo', 'nombre']


    class Meta:
        db_table = "formularios_usuario"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre_usuario

    @property
    def is_active(self):
        return self.activo
    
    def set_password(self, raw_password):
        from .services import hash_password
        self.password = hash_password(raw_password)
        self._password = raw_password
    
    def check_password(self, raw_password):
        from .services import verify_password
        return verify_password(self.password, raw_password)

class Formulario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, null=True, blank=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    permitir_fotos = models.BooleanField(default=False)
    permitir_gps = models.BooleanField(default=False)

    ESTADO_CHOICES = [
        ('Ingresada', 'Ingresada'),
        ('Activa', 'Activa'),
        ('Suspendida', 'Suspendida'),
        ('Pruebas', 'Pruebas'),
        ('Anulada', 'Anulada'),
    ]

    ENVIO_CHOICES = [
        ('En Linea/fuera Linea', 'En Linea/fuera Linea'),
        ('En Linea', 'En Linea'),
        ('Guardar', 'Guardar'),
    ]

    disponible_desde_fecha = models.DateField()
    disponible_hasta_fecha = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES)
    forma_envio = models.CharField(max_length=30, choices=ENVIO_CHOICES)
    es_publico = models.BooleanField(default=False)
    auto_envio = models.BooleanField(default=False)

    class Meta:
        # managed = False
        db_table = 'formularios_formulario'

class RolFormulario(models.Model):
    id_formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE)
    rol_id = models.ForeignKey(Rol, on_delete=models.CASCADE)

    class Meta:
        # managed = False
        db_table = "formularios_rol_formulario"


class RolUser(models.Model):
    id_rol = models.ForeignKey("formularios.Rol", on_delete=models.CASCADE, db_column="id_rol")
    nombre_de_usuario = models.ForeignKey("formularios.Usuario", on_delete=models.CASCADE,
                                          db_column="nombre_usuario", related_name="roles_enlace")
    class Meta:
        # managed = False
        db_table = "formularios_rol_user"
        unique_together = (("id_rol", "nombre_de_usuario"),)

class FormularioIndexVersion(models.Model):
    id_index_version = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # antes: formulario_id = models.ForeignKey(Formulario, on_delete=models.CASCADE)
    
    formulario_id = models.ForeignKey(
        Formulario,
        on_delete=models.CASCADE,
        db_column='formulario_id',   # <-- mapea al nombre físico correcto en la BD
        related_name='versiones'     # (opcional, útil en consultas)
    )

    class Meta:
        # managed = False
        db_table = "formularios_formularioindexversion" 

class Formulario_Index_Version(models.Model):
    # PK = id_index_version para permitir muchas filas por id_formulario
    id_index_version = models.OneToOneField(
        FormularioIndexVersion,
        on_delete=models.CASCADE,
        db_column="id_index_version",
        primary_key=True,
        related_name="row_historial",
    )
    id_formulario = models.ForeignKey(
        Formulario,
        on_delete=models.CASCADE,
        db_column="id_formulario",
        related_name="versiones_hist",
    )

    class Meta:
        # managed = False
        db_table = "formularios_formularios_index_version"

class Pagina(models.Model):
    id_pagina = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index_version = models.ForeignKey(
        FormularioIndexVersion, on_delete=models.CASCADE, related_name="paginas"
    )
    # antes: formulario_id = models.ForeignKey(Formulario, on_delete=models.CASCADE, related_name="paginas")
    formulario_id = models.ForeignKey(
        Formulario,
        on_delete=models.CASCADE,
        db_column='formulario_id',   # <-- mapea al nombre físico correcto
        related_name="paginas"
    )
    secuencia = models.PositiveIntegerField(default=1)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ["secuencia"]
        # managed = False
        db_table = "formularios_pagina"

# === Puntero: qué versión de formulario "contiene" cada página ===
class Pagina_Index_Version(models.Model):
    # Una fila por página (puntero ACTUAL). Copiamos ids a la nueva versión.
    id_pagina = models.OneToOneField(
        "formularios.Pagina",
        on_delete=models.CASCADE,
        db_column="id_pagina",
        primary_key=True,
        related_name="puntero_version",
    )
    id_index_version = models.ForeignKey(
        "formularios.FormularioIndexVersion",
        on_delete=models.CASCADE,
        db_column="id_index_version",
        related_name="paginas_puntero",
    )

    class Meta:
        # managed = False
        db_table = "formularios_pagina_index_version"


# === Historial de versiones por página (fecha de cambio) ===
class PaginaVersion(models.Model):
    id_pagina_version = models.CharField(primary_key=True, max_length=32, db_column="id_pagina_version")
    fecha_creacion = models.DateTimeField(db_column="fecha_creacion")
    id_pagina = models.CharField(max_length=32, db_column="id_pagina", null=True)

    class Meta:
        # managed = False
        db_table = "formularios_pagina_version"


class ClaseCampo(models.Model):
    clase = models.CharField(primary_key=True, max_length=30, db_column="clase")
    estructura = models.TextField(db_column="estructura", null=True, blank=True)

    class Meta:
        # managed = False
        db_table = "formularios_clase_campo"


class Campo(models.Model):
    id_campo = models.CharField(primary_key=True, max_length=32, db_column="id_campo")
    tipo = models.CharField(max_length=20, db_column="tipo")
    clase = models.CharField(max_length=30, db_column="clase")
    nombre_campo = models.CharField(max_length=64, db_column="nombre_campo")
    etiqueta = models.CharField(max_length=100, db_column="etiqueta")
    ayuda = models.CharField(max_length=255, db_column="ayuda", null=True, blank=True)
    config = models.TextField(db_column="config", null=True, blank=True)
    requerido = models.BooleanField(db_column="requerido", null=True)

    class Meta:
        # managed = False
        db_table = "formularios_campo"


class PaginaCampo(models.Model):
    # hack: usamos id_campo como pk a nivel ORM (la tabla real tiene pk compuesta)
    id_campo = models.ForeignKey(
        Campo, on_delete=models.CASCADE, db_column="id_campo",
        related_name="enlaces_pagina", primary_key=True
    )
    id_pagina_version = models.ForeignKey(
        PaginaVersion, on_delete=models.CASCADE, db_column="id_pagina_version",
        related_name="campos"
    )
    sequence = models.PositiveIntegerField(db_column="sequence", null=True)

    class Meta:
        # managed = False
        db_table = "formularios_pagina_campo"
        unique_together = (("id_campo", "id_pagina_version"),) 