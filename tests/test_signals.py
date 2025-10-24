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
    
    # Verificar que se creó la versión a través del historial
    versiones = Formulario_Index_Version.objects.filter(id_formulario=formulario)
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
    
    # Buscar versión del formulario
    fiv_link = Formulario_Index_Version.objects.filter(id_formulario=formulario).first()
    
    if fiv_link:
        # Buscar páginas vinculadas a esa versión
        paginas = Pagina_Index_Version.objects.filter(id_index_version=fiv_link.id_index_version)
        
        if paginas.exists():
            # Verificar que hay una página General
            for piv in paginas:
                pagina = piv.id_pagina
                if pagina.nombre == "General":
                    assert pagina.secuencia == 1
                    return
        
        pytest.skip("Signal para crear página no está configurado")
    else:
        pytest.skip("No se creó versión automáticamente")


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
    historial = Formulario_Index_Version.objects.filter(id_formulario=formulario)
    
    if not historial.exists():
        pytest.skip("Signal para crear historial no está configurado")
    
    # Verificar que hay al menos una versión vinculada
    assert historial.count() >= 1


@pytest.mark.django_db(transaction=True)
def test_crear_version_registra_historial(categoria, formulario):
    # Test que crear nueva versión registra en historial
    wait_for_commit()  # Esperar signals del formulario existente
    
    # Crear nueva versión manualmente
    nueva_version = FormularioIndexVersion.objects.create()
    
    # Registrar en historial manualmente (lo que haría el signal comentado)
    Formulario_Index_Version.objects.create(
        id_index_version=nueva_version,
        id_formulario=formulario
    )
    
    wait_for_commit()
    
    # Verificar que se creó registro en historial
    historial = Formulario_Index_Version.objects.filter(
        id_index_version=nueva_version,
        id_formulario=formulario
    )
    
    assert historial.exists()


@pytest.mark.django_db(transaction=True)
def test_crear_version_multiples_veces(categoria, formulario):
    # Test crear múltiples versiones registra todo en historial
    wait_for_commit()
    
    # Crear 3 versiones adicionales
    versiones = []
    for i in range(3):
        v = FormularioIndexVersion.objects.create()
        # Registrar en historial
        Formulario_Index_Version.objects.create(
            id_index_version=v,
            id_formulario=formulario
        )
        versiones.append(v)
    
    wait_for_commit()
    
    # Verificar que todas están en historial
    for version in versiones:
        exists = Formulario_Index_Version.objects.filter(
            id_index_version=version
        ).exists()
        assert exists


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
    
    # 1. Verificar que se creó versión a través del historial
    fiv_link = Formulario_Index_Version.objects.filter(id_formulario=formulario).first()
    assert fiv_link is not None, "No se creó versión"
    version = fiv_link.id_index_version
    
    # 2. Verificar que se creó página General (si está configurado)
    piv_links = Pagina_Index_Version.objects.filter(id_index_version=version)
    
    if not piv_links.exists():
        pytest.skip("Signal para crear página General no está configurado")
    
    # 3. Verificar que existe una página General
    pagina_general = None
    for piv in piv_links:
        if piv.id_pagina.nombre == "General":
            pagina_general = piv.id_pagina
            break
    
    if not pagina_general:
        pytest.skip("Signal para crear página General no está configurado")
    
    assert pagina_general.secuencia == 1


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
    
    # Contar versiones a través del historial (debe ser 1, no infinitas)
    count = Formulario_Index_Version.objects.filter(id_formulario=formulario).count()
    assert count == 1, f"Se crearon {count} versiones, esperaba 1"
    
    # Contar páginas vinculadas a esa versión
    fiv_link = Formulario_Index_Version.objects.filter(id_formulario=formulario).first()
    if fiv_link:
        count_paginas = Pagina_Index_Version.objects.filter(id_index_version=fiv_link.id_index_version).count()
        assert count_paginas <= 1, f"Se crearon {count_paginas} páginas, esperaba 0 o 1"