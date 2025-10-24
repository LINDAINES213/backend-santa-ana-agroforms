import os, json, random, string
from datetime import date, timedelta
from locust import HttpUser, task, between, events
import gevent.lock

HOST = os.getenv("HOST", "https://santa-ana-api.onrender.com")

LOGIN_PATH = "/api/auth/login/"
FORM_BASE  = "/api/formularios/"
PAGE_BASE  = "/api/paginas/"
PAGE_ADD_FIELD_ACTION = "campos"   # /api/paginas/{id}/campos/

# ---- Parseo de credenciales (user:pass,user2:pass2,...) ----
CRED_LIST = []
@events.test_start.add_listener
def _parse_creds(environment, **kw):
    raw = (os.getenv("API_USERS", "") or "").strip()
    pairs = [tuple(x.split(":", 1)) for x in raw.split(",") if ":" in x]
    environment.parsed_creds = pairs
    global CRED_LIST
    CRED_LIST = pairs

_rr_lock = gevent.lock.Semaphore()
_rr_idx = 0
def pick_cred():
    """Entrega una credencial distinta por VU (round-robin, thread-safe)."""
    global _rr_idx
    if not CRED_LIST:
        return (os.getenv("API_USER",""), os.getenv("API_PASS",""))
    with _rr_lock:
        u, p = CRED_LIST[_rr_idx % len(CRED_LIST)]
        _rr_idx += 1
        return u, p

def rstr(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

class WebUser(HttpUser):
    wait_time = between(0.2, 0.8)

    def on_start(self):
        self.client.headers.update({"Accept": "application/json"})
        self.auth_ok = False

        user, pwd = pick_cred()
        # Log simple en consola para verificar reparto
        print(f"[VU {id(self)}] usando credenciales de: {user}")

        with self.client.post(
            LOGIN_PATH,
            json={"nombre_usuario": user, "password": pwd},
            name="AUTH login",
            catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"{resp.status_code} {resp.text}"); return
            data = resp.json()
            token = data.get("access_token")
            if not token:
                resp.failure(f"sin access_token: {data}"); return
            self.client.headers["Authorization"] = f"Bearer {token}"
            resp.success(); self.auth_ok = True

    # -------- Helpers CRUD --------
    def _crear_formulario(self):
        hoy = date.today()
        body = {
            "nombre": f"Form {rstr()}",
            "descripcion": "locust",
            "permitir_fotos": True,
            "permitir_gps": True,
            "disponible_desde_fecha": hoy.isoformat(),
            "disponible_hasta_fecha": (hoy + timedelta(days=30)).isoformat(),
            "estado": "Activo",
            "forma_envio": "En Linea",
            "es_publico": False,
            "auto_envio": False,
        }
        r = self.client.post(FORM_BASE, json=body, name="POST /formularios/")
        return r.json().get("id") if r.status_code in (200, 201) else None

    def _agregar_pagina(self, form_id):
        # ¡Slash final obligatorio en acciones detalle!
        url = f"{FORM_BASE}{form_id}/agregar-pagina/"
        body = {"nombre": f"Pag {rstr()}", "descripcion": "locust page"}
        return self.client.post(url, json=body, name="POST /formularios/{id}/agregar-pagina/")

    def _agregar_campo_a_pagina(self, page_id):
        url = f"{PAGE_BASE}{page_id}/{PAGE_ADD_FIELD_ACTION}/"
        body = {
            "nombre_campo": f"campo_{rstr()}",
            "etiqueta": "Etiqueta prueba",
            "clase": "number",
            "ayuda": "Ayuda...",
            "requerido": True,
            "config": {"min": 31, "max": 87, "step": None, "unit": "$"}
        }
        return self.client.post(url, json=body, name="POST /paginas/{id}/campos/")

    # -------- Escenario principal (crear/editar/borrar) --------
    @task(3)
    def flujo_escritura(self):
        if not self.auth_ok: return

        form_id = self._crear_formulario()
        if not form_id: return
        self.client.get(f"{FORM_BASE}{form_id}/", name="GET /formularios/{id}/")

        rp = self._agregar_pagina(form_id)
        page_id = rp.json().get("id_pagina") if rp.status_code in (200,201) else None

        field_id = None
        if page_id:
            rc = self._agregar_campo_a_pagina(page_id)
            if rc.status_code in (200, 201):
                field_id = rc.json().get("id_campo")

        self.client.patch(f"{FORM_BASE}{form_id}/", json={"descripcion": "edit locust"},
                          name="PATCH /formularios/{id}/")
        if page_id:
            self.client.patch(f"{PAGE_BASE}{page_id}/", json={"descripcion": "edit page locust"},
                              name="PATCH /paginas/{id}/")
        if field_id:
            self.client.patch(f"/api/campos/{field_id}/", json={"etiqueta": "Etiqueta edit"},
                              name="PATCH /campos/{id}/")

        if field_id:
            self.client.delete(f"/api/campos/{field_id}/", name="DELETE /campos/{id}/")
        if page_id:
            self.client.delete(f"{PAGE_BASE}{page_id}/", name="DELETE /paginas/{id}/")
        self.client.delete(f"{FORM_BASE}{form_id}/", name="DELETE /formularios/{id}/")

    # -------- Lecturas --------
    @task(1)
    def solo_listas(self):
        if not self.auth_ok: return
        self.client.get(FORM_BASE, name="GET /formularios/")
        self.client.get(PAGE_BASE,  name="GET /paginas/")
