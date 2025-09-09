from django.db import models
import uuid

# Create your models here.

class Categoria(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return self.nombre

class Rol(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)

class Usuario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100)
    correo = models.EmailField(unique=True)
    contrasena = models.CharField(max_length=128)
    nombre_usuario = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="usuarios")

    class Meta:
        db_table = "formularios_usuario"  # 🔸 esta aún NO existe; Django la creará

    def __str__(self):
        estado = "Activo" if self.activo else "Inactivo"
        return f"{self.nombre} ({self.rol.nombre}) - {estado}"


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

class FormularioIndexVersion(models.Model):
    id_index_version = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

class Pagina(models.Model):
    id_pagina = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index_version = models.ForeignKey(
        FormularioIndexVersion, on_delete=models.CASCADE, related_name="paginas"
    )
    formulario = models.ForeignKey(
        Formulario, on_delete=models.CASCADE, related_name="paginas"
    )
    secuencia = models.PositiveIntegerField(default=1)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ["secuencia"]


class PaginaIndex(models.Model):
    id_index_version = models.ForeignKey(
        FormularioIndexVersion, on_delete=models.CASCADE, related_name="paginas_index"
    )
    id_pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name="indices")
    id_formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("id_index_version", "id_pagina")

try:
    from django.db.models import JSONField
except Exception:
    JSONField = None

class ClaseCampo(models.Model):
    clase = models.CharField(max_length=30, primary_key=True)  
    schema = JSONField(null=True, blank=True) if JSONField else models.TextField(null=True, blank=True)

    class Meta:
        db_table = "formularios_clase_campo2"

class Campo(models.Model):
    """
    Estructura de un campo dentro de una Página.
    Coincide con tu grid: id_campo, tipo, clase, nombre_campo, etiqueta, ayuda, config, requerido.
    """
    id_campo = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # FK a Pagina (UUID). Ajusta 'formularios.Pagina'
    pagina = models.ForeignKey("formularios.Pagina", on_delete=models.CASCADE, related_name="campos")

    tipo = models.CharField(max_length=20)    
    clase = models.CharField(max_length=20)    
    nombre_campo = models.CharField(max_length=120)          
    etiqueta = models.CharField(max_length=200)          
    ayuda = models.CharField(max_length=255, blank=True, default="")  
    config = JSONField(default=dict, blank=True) if JSONField else models.TextField(blank=True, default="{}")
    requerido = models.BooleanField(default=False)          
    sequence  = models.PositiveIntegerField(default=1)       
    creado     = models.DateTimeField(auto_now_add=True)
    actualizado= models.DateTimeField(auto_now=True)
    grupo = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="subcampos",
    )

    class Meta:
        db_table = "formularios_campo2"     # si ya tienes la tabla creada con otro nombre, ajusta aquí
        ordering = ["sequence", "id_campo"]
        indexes = [
            models.Index(fields=["pagina", "sequence"]),
            models.Index(fields=["pagina", "nombre_campo"]),
            models.Index(fields=["clase"]),
            models.Index(fields=["pagina", "grupo", "sequence"]),
        ]

    def __str__(self):
        return f"{self.pagina_id}:{self.nombre_campo} ({self.clase})"
    
import uuid
from django.db import models

class FormularioActualVersion(models.Model):
    """
    Una fila por formulario -> cuál FormularioIndexVersion está vigente.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formulario = models.OneToOneField(
        "formularios.Formulario",
        on_delete=models.CASCADE,
        related_name="version_activa",
    )
    index_version = models.ForeignKey(
        "formularios.FormularioIndexVersion",
        on_delete=models.CASCADE,
        related_name="asignaciones_activas",
    )
    publicada_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.formulario.nombre} → {self.index_version_id}"

class PaginaActualVersion(models.Model):
    """
    Intermedia SOLO de la versión vigente (FormularioIndexVersion ↔ Pagina).
    Proyección materializada de PaginaIndex para la versión activa.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version_activa = models.ForeignKey(
        "formularios.FormularioActualVersion",
        on_delete=models.CASCADE,
        related_name="paginas_actuales",
    )
    formulario = models.ForeignKey(
        "formularios.Formulario",
        on_delete=models.CASCADE,
        related_name="paginas_actuales",
    )
    pagina = models.ForeignKey(
        "formularios.Pagina",
        on_delete=models.CASCADE,
        related_name="links_actuales",
    )
    # orden = models.PositiveIntegerField(default=1)       
    fecha_creacion = models.DateTimeField()          

    class Meta:
        unique_together = (("version_activa", "pagina"))
        indexes = [
            models.Index(fields=["formulario"]),
            models.Index(fields=["version_activa"]),
        ]
        ordering = ["formulario_id"]

    def __str__(self):
        return f"{self.formulario_id} · {self.pagina_id}"

class PaginaCampoActual(models.Model):
    """
    Campos de la PÁGINA vigente (solo la versión actual).
    Se deriva de los Campos ligados a Pagina al activar una versión.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pagina_actual = models.ForeignKey(
        "formularios.PaginaActualVersion",
        on_delete=models.CASCADE,
        related_name="campos_actuales",
    )
    campo = models.ForeignKey(
        "formularios.Campo",
        on_delete=models.CASCADE,
        related_name="usos_actuales",
    )
    orden = models.PositiveIntegerField(default=1)       # copia de Campo.sequence
    requerido = models.BooleanField(default=False)       # copia de Campo.requerido
    config = (JSONField(default=dict, blank=True) if JSONField else
              models.TextField(blank=True, default="{}"))

    class Meta:
        unique_together = (("pagina_actual", "campo"), ("pagina_actual", "orden"))
        indexes = [models.Index(fields=["pagina_actual", "orden"])]
        ordering = ["pagina_actual_id", "orden"]

    def __str__(self):
        return f"{self.pagina_actual_id} · {self.campo_id} · #{self.orden}"
