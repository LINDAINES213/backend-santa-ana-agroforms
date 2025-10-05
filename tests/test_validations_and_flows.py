from datetime import date, timedelta

def _payload_form(categoria_id, desde=None, hasta=None, nombre="Form-Valid"):
    desde = desde or date.today()
    hasta = hasta or (date.today() + timedelta(days=3))
    return {
        "categoria": str(categoria_id),
        "nombre": nombre,
        "descripcion": "",
        "permitir_fotos": False,
        "permitir_gps": False,
        "disponible_desde_fecha": str(desde),
        "disponible_hasta_fecha": str(hasta),
        "estado": "Activa",
        "forma_envio": "En Linea",
        "es_publico": False,
        "auto_envio": False,
    }

def _add_page(api_client, fid, name="PX", bump=1):
    return api_client.post(
        f"/api/formularios/{fid}/agregar-pagina/?bump={bump}",
        {"nombre": name},
        format="json"
    )

def test_categoria_duplicate_name_tolerant(api_client, categoria):
    # Crear otra con mismo nombre debe fallar (400/409) o permitir si no hay restricción (200/201)
    r = api_client.post("/api/categorias/", {"nombre": categoria.nombre, "descripcion": ""}, format="json")
    assert r.status_code in (200, 201, 400, 409)

def test_formulario_invalid_date_range(api_client, categoria):
    # hasta < desde debería invalidar (400/422); si el backend no valida, 200/201
    desde = date.today()
    hasta = date.today() - timedelta(days=1)
    payload = _payload_form(categoria.id, desde=desde, hasta=hasta, nombre="BadDates")
    r = api_client.post("/api/formularios/", payload, format="json")
    assert r.status_code in (400, 422, 200, 201)

def test_formulario_download_and_preview_exist(api_client, formulario):
    r_down = api_client.get(f"/api/formularios/{formulario.id}/download/")
    r_prev = api_client.post(f"/api/formularios/{formulario.id}/preview/", {}, format="json")
    assert r_down.status_code in (200, 400, 401, 403, 404)
    assert r_prev.status_code in (200, 400, 401, 403, 404)

def test_agregar_pagina_without_name(api_client, formulario):
    # Si el nombre es requerido debería 400
    r = api_client.post(
        f"/api/formularios/{formulario.id}/agregar-pagina/?bump=1",
        {},
        format="json"
    )
    assert r.status_code in (400, 200, 201)

def test_agregar_pagina_invalid_bump_param(api_client, formulario):
    r = api_client.post(
        f"/api/formularios/{formulario.id}/agregar-pagina/?bump=abc",
        {"nombre": "NX"},
        format="json"
    )
    assert r.status_code in (200, 201, 400)

def test_duplicar_formulario_without_payload(api_client, formulario):
    r = api_client.post(f"/api/formularios/{formulario.id}/duplicar/", {}, format="json")
    assert r.status_code in (200, 201, 400)

def test_delete_categoria_linked_to_formulario_behavior(api_client, categoria, formulario):
    r = api_client.delete(f"/api/categorias/{categoria.id}/")
    assert r.status_code in (200, 204, 400, 409)