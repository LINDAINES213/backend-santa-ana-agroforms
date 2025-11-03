from django.core.files.uploadedfile import SimpleUploadedFile

def test_fuentes_datos_list_smoke(api_client):
    r = api_client.get("/api/fuentes-datos/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_fuentes_datos_reject_wrong_extension(api_client):
    # Debe rechazar .txt
    file_obj = SimpleUploadedFile("archivo.txt", b"contenido")
    payload = {"nombre": "FBad", "descripcion": "x", "archivo": file_obj}
    r = api_client.post("/api/fuentes-datos/", payload)
    assert r.status_code in (400, 415)

def test_fuentes_datos_detail_404(api_client):
    r = api_client.get("/api/fuentes-datos/00000000-0000-0000-0000-000000000000/")
    assert r.status_code in (404, 400)
