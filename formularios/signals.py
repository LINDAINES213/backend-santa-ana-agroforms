from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction


from formularios.services import activar_version
from .models import Formulario, FormularioIndexVersion


# @receiver(post_save, sender=Formulario)
# def crear_version_inicial(sender, instance, created, **kwargs):
#     if created:
#         v1 = FormularioIndexVersion.objects.create(formulario=instance)
#         # activar versión inicial (aunque no tenga páginas todavía)
#         activar_version(instance, v1)

@receiver(post_save, sender=Formulario)
def crear_y_activar_version_inicial(sender, instance: Formulario, created, **kwargs):
    """
    Al crear un Formulario: crea v1 y la deja activa.
    """
    if created:
        v1 = FormularioIndexVersion.objects.create(formulario=instance)
        # Activa v1 para que las tablas *_Actual queden listas
        activar_version(instance, v1)


@receiver(post_save, sender=FormularioIndexVersion)
def auto_activar_version_mas_reciente(sender, instance: FormularioIndexVersion, created, **kwargs):
    """
    Al crear CUALQUIER nueva versión del formulario, la activa automáticamente
    si es la más reciente por fecha_creacion (normalmente lo será).
    """
    if not created:
        return

    form = instance.formulario

    # Obten la más reciente por fecha_creacion (desc)
    newest = (FormularioIndexVersion.objects
              .filter(formulario=form)
              .order_by("-fecha_creacion")
              .first())

    # Por sanidad: solo activar si la que acaba de crearse es efectivamente la más nueva
    if newest and newest.id_index_version == instance.id_index_version:
        # Activa y materializa PaginaIndexActual / PaginaCampoActual
        activar_version(form, instance)

@receiver(post_save, sender=FormularioIndexVersion)
def auto_activar_version_mas_reciente(sender, instance: FormularioIndexVersion, created, **kwargs):
    if not created:
        return

    form = instance.formulario

    def _activate():
        # activar solo si sigue siendo la más reciente
        newest = (FormularioIndexVersion.objects
                  .filter(formulario=form)
                  .order_by("-fecha_creacion")
                  .first())
        if newest and newest.id_index_version == instance.id_index_version:
            activar_version(form, instance)

    # ✅ activa al commit, cuando ya existen PaginaIndex y campos clonados
    transaction.on_commit(_activate)