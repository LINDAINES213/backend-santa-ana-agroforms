from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Formulario, FormularioIndexVersion

@receiver(post_save, sender=Formulario)
def crear_version_inicial(sender, instance, created, **kwargs):
    if created:
        FormularioIndexVersion.objects.create(formulario=instance)