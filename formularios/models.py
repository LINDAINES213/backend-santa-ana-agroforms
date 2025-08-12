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
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True)

class Usuario(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    correo = models.EmailField(unique=True)
    contrasena = models.CharField(max_length=128)
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE)

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
    color_fondo = models.CharField(max_length=20, blank=True)
    color_texto = models.CharField(max_length=20, blank=True)

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