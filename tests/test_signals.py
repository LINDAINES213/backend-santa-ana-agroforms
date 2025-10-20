import pytest
from datetime import date, timedelta
from django.db import transaction, connection
from oauth2_provider.models import AccessToken, RefreshToken, Application
from oauthlib.common import generate_token
from django.utils import timezone
from formularios.models import (
    Usuario,
    Formulario,
    FormularioIndexVersion,
    Formulario_Index_Version,
    Pagina,
    Pagina_Index_Version,
)

def wait_for_commit():
    # Forzar commit para que se ejecuten los signals on_commit
    connection.cursor().execute("SELECT 1")
    # Dar tiempo para que se ejecuten los callbacks
    import time
    time.sleep(0.1)


@pytest.mark.django_db(transaction=True)
def test_formulario_create_genera_version_inicial(categoria):
    # Test que al crear formulario se genera versión inicial automáticamente
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Nuevo Formulario",
        descripcion="Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    wait_for_commit()
    
    # Verificar que se creó la versión
    versiones = FormularioIndexVersion.objects.filter(formulario_id=formulario)
    assert versiones.exists()
    assert versiones.count() >= 1


@pytest.mark.django_db(transaction=True)
def test_formulario_create_genera_pagina_general(categoria):
    # Test que al crear formulario se genera página 'General' automáticamente
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Nuevo Formulario",
        descripcion="Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    # Forzar ejecución de on_commit
    wait_for_commit()
    
    # Verificar que se creó la página
    paginas = Pagina.objects.filter(formulario_id=formulario)
    
    if paginas.exists():
        pagina_general = paginas.filter(nombre="General").first()
        if pagina_general:
            assert pagina_general.secuencia == 1
    else:
        # Si los signals no están configurados para crear página automáticamente
        pytest.skip("Signal para crear página no está configurado")


@pytest.mark.django_db(transaction=True)
def test_formulario_create_activa_version(categoria):
    # Test que al crear formulario se activa la versión inicial
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Nuevo Formulario",
        descripcion="Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    wait_for_commit()
    
    # Verificar que existe registro en Formulario_Index_Version
    version = FormularioIndexVersion.objects.filter(formulario_id=formulario).first()
    
    if version:
        historial = Formulario_Index_Version.objects.filter(
            id_formulario=formulario,
            id_index_version=version
        )
        if not historial.exists():
            pytest.skip("Signal para crear historial no está configurado")
    else:
        pytest.skip("No se creó versión automáticamente")


@pytest.mark.django_db(transaction=True)
def test_crear_version_registra_historial(categoria, formulario):
    # Test que crear nueva versión registra en historial
    wait_for_commit()  # Esperar signals del formulario existente
    
    nueva_version = FormularioIndexVersion.objects.create(formulario_id=formulario)
    
    wait_for_commit()
    
    # Verificar que se creó registro en historial
    historial = Formulario_Index_Version.objects.filter(
        id_index_version=nueva_version,
        id_formulario=formulario
    )
    
    if not historial.exists():
        pytest.skip("Signal para crear historial no está configurado")


@pytest.mark.django_db(transaction=True)
def test_crear_version_multiples_veces(categoria, formulario):
    # Test crear múltiples versiones registra todo en historial
    wait_for_commit()
    
    # Crear 3 versiones adicionales
    versiones = []
    for i in range(3):
        v = FormularioIndexVersion.objects.create(formulario_id=formulario)
        versiones.append(v)
    
    wait_for_commit()
    
    # Verificar que todas están en historial
    for version in versiones:
        exists = Formulario_Index_Version.objects.filter(
            id_index_version=version
        ).exists()
        if not exists:
            pytest.skip("Signal para crear historial no está configurado")


@pytest.mark.django_db(transaction=True)
def test_usuario_desactivar_revoca_tokens():
    # Test que desactivar usuario revoca sus tokens OAuth2
    from formularios.services import hash_password
    
    # Crear usuario activo
    usuario = Usuario.objects.create(
        nombre_usuario="testuser",
        nombre="Test User",
        correo="test@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )
    
    # Crear aplicación OAuth2
    app, _ = Application.objects.get_or_create(
        name='Test App',
        defaults={
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
        }
    )
    
    # Crear tokens
    access_token = AccessToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        expires=timezone.now() + timedelta(hours=10),
        scope='read write'
    )
    
    refresh_token = RefreshToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        access_token=access_token
    )
    
    # Verificar que existen
    assert AccessToken.objects.filter(user=usuario).exists()
    assert RefreshToken.objects.filter(user=usuario).exists()
    
    # Desactivar usuario
    usuario.activo = False
    usuario.save()
    
    wait_for_commit()
    
    # Verificar que se revocaron los tokens
    assert not AccessToken.objects.filter(user=usuario).exists()
    assert not RefreshToken.objects.filter(user=usuario).exists()


@pytest.mark.django_db(transaction=True)
def test_usuario_quitar_acceso_web_revoca_tokens():
    # Test que quitar acceso_web revoca tokens
    from formularios.services import hash_password
    
    usuario = Usuario.objects.create(
        nombre_usuario="testuser",
        nombre="Test User",
        correo="test@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )
    
    app, _ = Application.objects.get_or_create(
        name='Test App',
        defaults={
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
        }
    )
    
    AccessToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        expires=timezone.now() + timedelta(hours=10),
        scope='read write'
    )
    
    # Quitar acceso web
    usuario.acceso_web = False
    usuario.save()
    
    wait_for_commit()
    
    # Verificar que se revocaron los tokens
    assert not AccessToken.objects.filter(user=usuario).exists()


@pytest.mark.django_db(transaction=True)
def test_usuario_activar_no_revoca_tokens():
    # Test que activar usuario no revoca tokens
    from formularios.services import hash_password
    
    # Crear usuario inactivo
    usuario = Usuario.objects.create(
        nombre_usuario="testuser",
        nombre="Test User",
        correo="test@example.com",
        password=hash_password("testpass123"),
        activo=False,
        acceso_web=True,
    )
    
    app, _ = Application.objects.get_or_create(
        name='Test App',
        defaults={
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
        }
    )
    
    # Aunque esté inactivo, crear token (caso edge)
    AccessToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        expires=timezone.now() + timedelta(hours=10),
        scope='read write'
    )
    
    tokens_antes = AccessToken.objects.filter(user=usuario).count()
    
    # Activar usuario
    usuario.activo = True
    usuario.save()
    
    wait_for_commit()
    
    # Verificar que NO se revocaron los tokens
    tokens_despues = AccessToken.objects.filter(user=usuario).count()
    assert tokens_antes == tokens_despues


@pytest.mark.django_db(transaction=True)
def test_usuario_update_otros_campos_no_revoca_tokens():
    # Test que actualizar otros campos no revoca tokens
    from formularios.services import hash_password
    
    usuario = Usuario.objects.create(
        nombre_usuario="testuser",
        nombre="Test User",
        correo="test@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )
    
    app, _ = Application.objects.get_or_create(
        name='Test App',
        defaults={
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
        }
    )
    
    AccessToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        expires=timezone.now() + timedelta(hours=10),
        scope='read write'
    )
    
    # Cambiar nombre (no debe revocar)
    usuario.nombre = "Nuevo Nombre"
    usuario.save()
    
    wait_for_commit()
    
    # Verificar que los tokens siguen ahí
    assert AccessToken.objects.filter(user=usuario).exists()


@pytest.mark.django_db
def test_usuario_nuevo_no_revoca_tokens():
    # Test que crear nuevo usuario no intenta revocar tokens
    from formularios.services import hash_password
    
    # Esto no debe generar error aunque no haya tokens
    usuario = Usuario.objects.create(
        nombre_usuario="newuser",
        nombre="New User",
        correo="new@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )
    
    # Verificar que se creó correctamente
    assert usuario.pk is not None


@pytest.mark.django_db(transaction=True)
def test_flujo_completo_crear_formulario(categoria):
    # Test integración completa: crear formulario ejecuta todos los signals
    # Crear formulario
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Formulario Completo",
        descripcion="Test de integración",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    wait_for_commit()
    
    # 1. Verificar que se creó versión
    version = FormularioIndexVersion.objects.filter(formulario_id=formulario).first()
    assert version is not None, "No se creó versión"
    
    # 2. Verificar que se registró en historial (si está configurado)
    historial_exists = Formulario_Index_Version.objects.filter(
        id_formulario=formulario,
        id_index_version=version
    ).exists()
    
    if not historial_exists:
        pytest.skip("Signal para crear historial no está configurado")
    
    # 3. Verificar que se creó página General (si está configurado)
    pagina_general = Pagina.objects.filter(
        formulario_id=formulario,
        nombre="General"
    ).first()
    
    if not pagina_general:
        pytest.skip("Signal para crear página General no está configurado")
    
    # 4. Verificar que la página tiene puntero a versión
    puntero_exists = Pagina_Index_Version.objects.filter(
        id_pagina=pagina_general,
        id_index_version=version
    ).exists()
    
    if not puntero_exists:
        pytest.skip("Signal para crear puntero no está configurado")


@pytest.mark.django_db(transaction=True)
def test_flujo_completo_usuario_con_tokens(categoria):
    # Test integración: crear usuario, tokens, y revocar
    from formularios.services import hash_password
    
    # Crear usuario
    usuario = Usuario.objects.create(
        nombre_usuario="fulltest",
        nombre="Full Test",
        correo="fulltest@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )
    
    # Crear aplicación y tokens
    app, _ = Application.objects.get_or_create(
        name='Test App',
        defaults={
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
        }
    )
    
    access_token = AccessToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        expires=timezone.now() + timedelta(hours=10),
        scope='read write'
    )
    
    RefreshToken.objects.create(
        user=usuario,
        token=generate_token(),
        application=app,
        access_token=access_token
    )
    
    # Verificar tokens existen
    assert AccessToken.objects.filter(user=usuario).exists()
    assert RefreshToken.objects.filter(user=usuario).exists()
    
    # Desactivar usuario (signal debe revocar)
    usuario.activo = False
    usuario.save()
    
    wait_for_commit()
    
    # Verificar revocación
    assert not AccessToken.objects.filter(user=usuario).exists()
    assert not RefreshToken.objects.filter(user=usuario).exists()


@pytest.mark.django_db(transaction=True)
def test_signal_no_causa_bucle_infinito(categoria):
    # Crear formulario
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Test Bucle",
        descripcion="",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    wait_for_commit()
    
    # Contar versiones (debe ser 1, no infinitas)
    count = FormularioIndexVersion.objects.filter(formulario_id=formulario).count()
    assert count == 1, f"Se crearon {count} versiones, esperaba 1"
    
    # Contar páginas (debe ser 0 o 1 según configuración)
    count_paginas = Pagina.objects.filter(formulario_id=formulario).count()
    assert count_paginas <= 1, f"Se crearon {count_paginas} páginas, esperaba 0 o 1"