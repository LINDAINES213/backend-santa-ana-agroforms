from formularios.models import Rol

def test_roles_crud_basic(api_client, db):
    r = api_client.post('/api/roles/', {'nombre': 'admin', 'descripcion': ''}, format='json')
    assert r.status_code in (200, 201), r.data
    rid = r.data['id']

    r2 = api_client.get('/api/roles/')
    assert r2.status_code == 200
    assert any(x['nombre'] == 'admin' for x in r2.json())

    r3 = api_client.patch(f'/api/roles/{rid}/', {'descripcion': 'root'}, format='json')
    assert r3.status_code == 200 and r3.data['descripcion'] == 'root'

def _create_rol(api_client):
    r = api_client.post('/api/roles/', {'nombre':'op','descripcion':''}, format='json')
    assert r.status_code in (200,201)
    return r.data['id']

def test_user_create_and_list(api_client, db):
    rol_id = _create_rol(api_client)
    payload = {
        "nombre": "María",
        "correo": "maria@gmail.com",
        "contrasena": "mar14#$po",
        "nombre_usuario": "mariah",
        "activo": True,
        "rol": str(rol_id),
    }
    r = api_client.post('/api/usuarios/', payload, format='json')
    assert r.status_code in (200, 201), r.data

    r2 = api_client.get('/api/usuarios/')
    assert r2.status_code == 200
    assert any(u['nombre'] == 'María' for u in r2.json())

def test_user_serializer_includes_rol_name(api_client, db):
    rid = _create_rol(api_client)
    payload = {
        "nombre": "Juan",
        "correo": "juangalvez@hotmail.com",
        "contrasena": "contra5eNa%",
        "nombre_usuario": "juanito",
        "activo": True,
        "rol": str(rid),
    }
    r = api_client.post('/api/usuarios/', payload, format='json')
    assert r.status_code in (200,201)
    uid = r.data['id']

    r2 = api_client.get(f'/api/usuarios/{uid}/')
    assert r2.status_code == 200
    assert 'rol_nombre' in r2.data

def test_username_unique(api_client, db):
    rid = _create_rol(api_client)
    base = {
        "correo": "abcderf@outlook.com",
        "contrasena": "Te5T#",
        "activo": True,
        "rol": str(rid),
    }
    p1 = dict(base, nombre="U1", nombre_usuario="taken")
    p2 = dict(base, nombre="U2", nombre_usuario="taken", correo="berto@outlook.com")
    r1 = api_client.post('/api/usuarios/', p1, format='json')
    r2 = api_client.post('/api/usuarios/', p2, format='json')
    assert r1.status_code in (200,201)
    assert r2.status_code in (400,422)
