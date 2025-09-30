from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Formulario, FormularioIndexVersion, Formulario_Index_Version, Pagina

from .services import activar_version

@receiver(post_save, sender=Formulario)
def crear_y_activar_version_inicial(sender, instance: Formulario, created, **kwargs):
    if created:
        # 1) crear v1 del formulario
        v1 = FormularioIndexVersion.objects.create(formulario_id=instance)

        def _despues_commit():
            # 2) crear página inicial en v1
            Pagina.objects.create(
                index_version=v1,
                formulario_id=instance,
                secuencia=1,
                nombre="General",
                descripcion="",
            )
            # 3) (opcional) actualizar índices/punteros
            activar_version(instance, v1)

        # Ejecutar cuando la creación de v1 ya quedó confirmada
        transaction.on_commit(_despues_commit)

@receiver(post_save, sender=FormularioIndexVersion)
def _registrar_historial_al_crear_version(sender, instance: FormularioIndexVersion, created, **kwargs):
    """
    En cuanto se crea una nueva FormularioIndexVersion, guardamos UNA fila en el historial
    (formularios_formularios_index_version) usando los nombres reales de columnas:
      - id_index_version (PK 1:1 con la versión)
      - id_formulario (FK al formulario)
    """
    if not created:
        return

    # Insertar en historial inmediatamente (si ya existiera, no duplica)
    def _do():
        Formulario_Index_Version.objects.get_or_create(
            id_index_version=instance,                       # PK = versión
            defaults={"id_formulario": instance.formulario_id},
        )

        # --- (OPCIONAL) actualizar puntero de versión activa si tienes esa tabla ---
        try:
            from django.apps import apps
            FormularioIndex = apps.get_model("formularios", "FormularioIndex")
        except Exception:
            FormularioIndex = None

        if FormularioIndex:
            FormularioIndex.objects.update_or_create(
                id_formulario=instance.formulario_id,
                defaults={"id_index_version": instance},
            )

    # Asegura que se ejecute cuando la transacción que creó la versión ya esté confirmada
    transaction.on_commit(_do)

from django.db.models.signals import post_save
from django.dispatch import receiver
from oauth2_provider.models import AccessToken, RefreshToken
from .models import Usuario

@receiver(post_save, sender=Usuario)
def revoke_tokens_when_flags_change(sender, instance: Usuario, **kwargs):
    if (not instance.acceso_web) or (not instance.activo):
        AccessToken.objects.filter(user=instance).delete()
        RefreshToken.objects.filter(user=instance).delete()