from django.db import models

# Create your models here.

class Formulario(models.Model):
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

class Grupo(models.Model):
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE, related_name='grupos')
    nombre = models.CharField(max_length=255)

class Campo(models.Model):
    TIPO_CHOICES = [
        ('texto', 'Texto'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('booleano', 'Booleano'),
    ]
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE, related_name='campos')
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE, related_name='campos', null=True, blank=True)
    
    nombre_campo = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    requerido = models.BooleanField(default=False)

