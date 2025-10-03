# # services.py
import json
import uuid
from django.db import transaction, connection

from django.apps import apps
from typing import Dict, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
import re
from argon2.low_level import hash_secret, verify_secret, Type
from os import urandom

from .models import (
    Formulario,
    FormularioIndexVersion,
    Pagina,
    PaginaVersion,
    ClaseCampo,
    Campo,
    PaginaCampo,
    Pagina_Index_Version
)
from formularios import models

def _uuid32_no_dashes(s: str) -> str:
    s = s.strip().lower()
    # si ya viene sin guiones (32 hex), devuélvelo
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return s
    # si viene con guiones (8-4-4-4-12), quítalos
    s = s.replace("-", "")
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return s
    raise ValueError("id_pagina inválido: debe ser UUID v4.")

# en serializers.py (arriba)
def uuid32(u) -> str:
    # acepta uuid.UUID o str
    s = str(u)
    return s.replace("-", "").lower()  # 32 chars


@transaction.atomic
def activar_version(formulario, nueva_version) -> None:
    Formulario_Index_Version = apps.get_model("formularios", "Formulario_Index_Version")

    # 1) HISTORIAL: asegurarnos de que EXISTA una fila por cada nueva versión
    #    (si ya existe esa fila, no se duplica)
    Formulario_Index_Version.objects.get_or_create(
        id_index_version=nueva_version,                 # PK por versión
        defaults={"id_formulario": formulario},
    )

    # 2) (OPCIONAL) Puntero a versión ACTIVA:
    #    Si quieres además mantener una tabla aparte con SOLO la versión activa,
    #    deja este bloque tal cual apuntando a tu tabla/Modelo 'FormularioIndex' (si existe).
    try:
        FormularioIndex = apps.get_model("formularios", "FormularioIndex")
    except LookupError:
        FormularioIndex = None

    if FormularioIndex:
        # aquí sí usamos update_or_create por formulario para mantener "solo 1 activa"
        FormularioIndex.objects.update_or_create(
            id_formulario=formulario,
            defaults={"id_index_version": nueva_version},
        )

    # 3) (Opcional) PaginaIndex análogo...
    try:
        PaginaIndex = apps.get_model("formularios", "PaginaIndex")
    except LookupError:
        PaginaIndex = None

    if PaginaIndex:
        from .models import Pagina
        for p in Pagina.objects.filter(index_version=nueva_version).only("id_pagina"):
            PaginaIndex.objects.update_or_create(
                id_pagina=p,
                defaults={
                    "id_index_version": nueva_version,
                    "id_formulario": formulario,
                },
            )

_CLASE_A_TIPO = {
    "string":  "texto",
    "text":    "texto",
    "list":    "texto",
    "hour":    "texto",
    "group":   "texto",
    "date":    "texto",
    "number":  "numerico",
    "calc":    "numerico",
    "boolean": "booleano",
    "firm":    "imagen",
    "dataset": "texto",
}

def _resolver_tipo_por_clase(clase: str) -> str:
    return _CLASE_A_TIPO.get((clase or "").strip().lower(), "texto")

def _ultima_pagina_version(pagina: Pagina) -> PaginaVersion | None:
    return (PaginaVersion.objects
            .filter(id_pagina=pagina)
            .order_by("-fecha_creacion")
            .first())

@transaction.atomic
def crear_campo_y_versionar_pagina(pagina: Pagina, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea Campo (tipo por clase) y publica nueva versión:
      - nueva FormularioIndexVersion
      - nueva PaginaVersion (fecha)
      - NO clona campos existentes, solo agrega el nuevo
      - actualiza punteros Pagina_Index_Version a la nueva index_version
    """
    clase = (data.get("clase") or "").strip().lower()
    if not clase:
        raise ValidationError("El campo 'clase' es obligatorio.")

    if not ClaseCampo.objects.filter(clase=clase).exists():
        raise ValidationError(f"La clase '{clase}' no existe en formularios_clase_campo.")

    tipo = _resolver_tipo_por_clase(clase)

    cfg = data.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg or "{}")
        except Exception:
            raise ValidationError("El campo 'config' debe ser JSON válido.")

    # 0) Crear el catálogo Campo
    campo = Campo.objects.create(
        tipo=tipo,
        clase=clase,
        nombre_campo=(data.get("nombre_campo") or f"{clase}_{timezone.now().strftime('%H%M%S')}").strip(),
        etiqueta=(data.get("etiqueta") or "").strip(),
        ayuda=(data.get("ayuda") or "").strip(),
        config=cfg,
        requerido=bool(data.get("requerido", False)),
    )

    # 1) Nueva versión de formulario
    formulario = pagina.formulario_id
    nueva_version = FormularioIndexVersion.objects.create(formulario_id=formulario)

    # 2) Nueva PaginaVersion para ESTA página
    prev_pv = _ultima_pagina_version(pagina)
    nueva_pv = PaginaVersion.objects.create(id_pagina=pagina)

    # 3) **CAMBIO CRÍTICO**: NO clonar campos existentes
    # Solo calcular la secuencia basada en los campos existentes
    max_seq = 0
    if prev_pv:
        # Solo obtener el número máximo de secuencia, NO clonar los campos
        max_seq_result = (PaginaCampo.objects
                         .filter(id_pagina_version=prev_pv)
                         .aggregate(max_seq=models.Max('sequence')))
        max_seq = max_seq_result.get('max_seq') or 0

    # 4) Insertar SOLO el NUEVO campo en la nueva PaginaVersion
    sequence = data.get("sequence")
    try:
        sequence = int(sequence) if sequence is not None else None
    except Exception:
        sequence = None

    if sequence is None:
        sequence = (max_seq + 1) if max_seq else 1

    PaginaCampo.objects.create(
        id_campo=campo,
        id_pagina_version=nueva_pv,
        sequence=sequence,
    )

    # 5) Actualizar punteros de TODAS las páginas del formulario a la nueva index_version
    for p in Pagina.objects.filter(formulario_id=formulario).only("id_pagina"):
        Pagina_Index_Version.objects.update_or_create(
            id_pagina=p,
            defaults={"id_index_version": nueva_version},
        )

    return {
        "campo_id": str(campo.id_campo),
        "formulario_id": str(formulario.id),
        "pagina_id": str(pagina.id_pagina),
        "nueva_version_id": str(nueva_version.id_index_version),
        "pagina_version_id": str(nueva_pv.id_pagina_version),
        "sequence": sequence,
    }
    
TIPO_POR_CLASE = {
    "number": "number",
    "boolean": "boolean",
    "text": "text",
    "string": "text",
    "date": "date",
    "hour": "hour",
    "list": "list",
    "group": "group",
    "calc": "calc",
    "dataset": "dataset",
    "firm": "firm",
}

def _uuid32() -> str:
    return uuid.uuid4().hex  # 32 chars, coincide con char(32)

# def _pagina_version_actual_o_nueva(id_pagina: str) -> PaginaVersion:
#     id_pagina_32 = _uuid32_no_dashes(id_pagina)

#     pv = (PaginaVersion.objects
#           .filter(id_pagina=id_pagina_32)
#           .order_by("-fecha_creacion")
#           .first())
#     if pv:
#         return pv

#     nuevo_id = _uuid32()  # ya devuelve 32 sin guiones
#     with connection.cursor() as cur:
#         cur.execute(
#             """
#             INSERT INTO formularios_pagina_version (id_pagina_version, fecha_creacion, id_pagina)
#             VALUES (%s, SYSUTCDATETIME(), %s)
#             """,
#             [nuevo_id, id_pagina_32],
#         )
#     return PaginaVersion(id_pagina_version=nuevo_id, id_pagina=id_pagina_32)

def _pagina_version_actual_o_nueva(id_pagina: str) -> PaginaVersion:
    id_pagina_32 = _uuid32_no_dashes(id_pagina)

    pv = (PaginaVersion.objects
          .filter(id_pagina=id_pagina_32)
          .order_by("-fecha_creacion")
          .first())
    if pv:
        return pv

    nuevo_id = _uuid32()  # 32 chars
    # Crear con ORM y timestamp desde Django (UTC si tu TZ settings están así)
    pv = PaginaVersion.objects.create(
        id_pagina_version=nuevo_id,
        fecha_creacion=timezone.now(),   # <-- reemplaza SYSUTCDATETIME()
        id_pagina=id_pagina_32,
    )
    return pv

def _siguiente_sequence(id_pagina_version: str) -> int:
    # with connection.cursor() as cur:
    #     cur.execute(
    #         """
    #         SELECT COALESCE(MAX("sequence"), 0)
    #         FROM formularios_pagina_campo
    #         WHERE id_pagina_version = %s
    #         """,
    #         [id_pagina_version],
    #     )
    #     (mx,) = cur.fetchone()
    from django.db.models import Max
    mx = (PaginaCampo.objects
        .filter(id_pagina_version=id_pagina_version)
        .aggregate(Max('sequence'))['sequence__max'] or 0)
    return int(mx) + 1

@transaction.atomic
def crear_campo_en_pagina(id_pagina: str, payload: dict) -> dict:
    # 0) validar/normalizar datos
    clase = payload["clase"]
    if not ClaseCampo.objects.filter(pk=clase).exists():
        raise ValueError(f"La clase '{clase}' no existe en formularios_clase_campo.")
    tipo = TIPO_POR_CLASE.get(clase, clase)

    nombre_campo = payload["nombre_campo"]
    etiqueta = payload["etiqueta"]
    ayuda = payload.get("ayuda")
    requerido = payload.get("requerido", None)

    cfg = payload.get("config")
    if isinstance(cfg, (dict, list)):
        cfg = json.dumps(cfg, ensure_ascii=False)

    # 1) crear registro en formularios_campo
    id_campo = _uuid32()
    Campo.objects.create(
        id_campo=id_campo,
        tipo=tipo,
        clase=clase,
        nombre_campo=nombre_campo,
        etiqueta=etiqueta,
        ayuda=ayuda,
        config=cfg,
        requerido=requerido,
    )

    # 2) obtener o crear versión de página
    pv = _pagina_version_actual_o_nueva(id_pagina)

    # 3) calcular sequence (si no viene)
    seq = payload.get("sequence")
    if not seq:
        seq = _siguiente_sequence(pv.id_pagina_version)

    # 4) insertar en formularios_pagina_campo
    with connection.cursor() as cur:
        # cur.execute(
        #     """
        #     INSERT INTO formularios_pagina_campo (id_campo, id_pagina_version, [sequence])
        #     VALUES (%s, %s, %s)
        #     """,
        #     [id_campo, pv.id_pagina_version, seq],
        # )
        cur.execute(
            """
            INSERT INTO formularios_pagina_campo (id_campo, id_pagina_version, "sequence")
            VALUES (%s, %s, %s)
            """,
            [id_campo, pv.id_pagina_version, seq],
        )

    return {
        "id_campo": id_campo,
        "tipo": tipo,
        "clase": clase,
        "nombre_campo": nombre_campo,
        "etiqueta": etiqueta,
        "id_pagina": id_pagina,
        "id_pagina_version": pv.id_pagina_version,
        "sequence": seq,
    }

def hash_password(plain: str) -> str:
    salt = urandom(16)
    phc = hash_secret(
        secret=plain.encode("utf-8"),
        salt=salt,
        time_cost=3,
        memory_cost=65536,   # 64 MiB
        parallelism=1,
        hash_len=32,
        type=Type.ID,
        version=19,
    )
    return phc.decode("utf-8")

def verify_password(hash_phc: str, plain: str) -> bool:
    return verify_secret(hash_phc.encode("utf-8"), plain.encode("utf-8"), Type.ID)

from django.db import transaction
from django.utils import timezone
import uuid

from .models import (
    Formulario, FormularioIndexVersion, Pagina, PaginaVersion,
    PaginaCampo, Campo
)
from .services import _uuid32, _uuid32_no_dashes  # ya existen en tu módulo


@transaction.atomic
def duplicar_formulario(formulario: Formulario, nuevo_nombre: str | None = None) -> Formulario:
    # 1) crear clon de formulario
    clon = Formulario.objects.create(
        categoria=formulario.categoria,
        nombre=nuevo_nombre or f"{formulario.nombre}_Copia",
        descripcion=formulario.descripcion,
        permitir_fotos=formulario.permitir_fotos,
        permitir_gps=formulario.permitir_gps,
        disponible_desde_fecha=formulario.disponible_desde_fecha,
        disponible_hasta_fecha=formulario.disponible_hasta_fecha,
        estado=formulario.estado,
        forma_envio=formulario.forma_envio,
        es_publico=formulario.es_publico,
        auto_envio=formulario.auto_envio,
    )

    # 2) crear versión de índice para el CLON
    idx_clon = FormularioIndexVersion.objects.create(formulario_id=clon)

    # 3) páginas "vigentes" del original (según su última versión)
    idx_orig = (FormularioIndexVersion.objects
                .filter(formulario_id=formulario)
                .order_by("-fecha_creacion")
                .first())

    if idx_orig:
        page_ids = (Pagina_Index_Version.objects
                    .filter(id_index_version=idx_orig)
                    .values_list("id_pagina", flat=True))
        paginas_origen = Pagina.objects.filter(id_pagina__in=page_ids).order_by("secuencia")
    else:
        # fallback si el original no tiene versiones creadas aún
        paginas_origen = Pagina.objects.filter(formulario_id=formulario).order_by("secuencia")

    # 4) clonar páginas y su ÚLTIMA versión con sus campos
    for p in paginas_origen:
        # 4.1) crear Pagina NUEVA en el clon
        p_nueva = Pagina.objects.create(
            index_version=idx_clon,           # versión donde "nace" en el clon
            formulario_id=clon,
            secuencia=p.secuencia,
            nombre=p.nombre,
            descripcion=p.descripcion,
        )

        # 4.2) apuntador vigente de la página del clon
        Pagina_Index_Version.objects.create(
            id_pagina=p_nueva,
            id_index_version=idx_clon,
        )

        # 4.3) tomar la ÚLTIMA PaginaVersion del original
        pid32 = _uuid32_no_dashes(str(p.id_pagina))
        pv_orig = (PaginaVersion.objects
                   .filter(id_pagina=pid32)
                   .order_by("-fecha_creacion")
                   .first())

        # 4.4) crear primera PaginaVersion del clon
        pv_nueva = PaginaVersion.objects.create(
            id_pagina_version=uuid32(uuid.uuid4()),
            id_pagina=_uuid32_no_dashes(str(p_nueva.id_pagina)),
            fecha_creacion=timezone.now(),
        )

        if pv_orig:
            # 4.5) clonar vínculos de campos (clonando CADA campo)
            links = (PaginaCampo.objects
                     .filter(id_pagina_version=pv_orig.id_pagina_version)
                     .order_by("sequence"))

            for l in links:
                c = l.id_campo
       

                c_nuevo = Campo.objects.create(
                    id_campo=uuid32(uuid.uuid4()),          # <- PK de 32 chars
                    tipo=c.tipo,
                    clase=c.clase,
                    nombre_campo=c.nombre_campo,       # si esto fuera UNIQUE y choca, añade sufijo
                    etiqueta=c.etiqueta,
                    ayuda=c.ayuda,
                    config=c.config,
                    requerido=c.requerido,
                )

                PaginaCampo.objects.create(
                    id_pagina_version=pv_nueva,        # <- pasa la INSTANCIA, no el string del id
                    id_campo=c_nuevo,                  # <- instancia
                    sequence=l.sequence,
                )

    return clon

def versionar_pagina_sin_clonar(pagina) -> PaginaVersion:
    """Crea una nueva PaginaVersion para 'pagina' reutilizando los mismos Campo (no clona)."""
    pid32 = _uuid32_no_dashes(str(pagina.id_pagina))

    prev = (
        PaginaVersion.objects
        .filter(id_pagina=pid32)
        .order_by('-fecha_creacion')
        .first()
    )

    nueva_pv = PaginaVersion.objects.create(
        id_pagina_version=uuid32(),
        id_pagina=pid32,
        fecha_creacion=timezone.now(),
    )

    if prev:
        links = (
            PaginaCampo.objects
            .filter(id_pagina_version=prev.id_pagina_version)
            .order_by('sequence')
        )
        PaginaCampo.objects.bulk_create([
            PaginaCampo(
                id_pagina_version=nueva_pv.id_pagina_version,
                id_campo=l.id_campo,          # ← MISMO Campo (id_campo estable)
                sequence=l.sequence
            )
            for l in links
        ])

    return nueva_pv
# @transaction.atomic
# def duplicar_formulario_orm(formulario_id) -> dict:
#     # 1) origen
#     f_src: Formulario = Formulario.objects.get(pk=formulario_id)

#     # 2) crea clon
#     f_dst = Formulario.objects.create(
#         id=uuid.uuid4(),
#         categoria=f_src.categoria,
#         nombre=f"{f_src.nombre}_Copia",
#         descripcion=f_src.descripcion,
#         permitir_fotos=f_src.permitir_fotos,
#         permitir_gps=f_src.permitir_gps,
#         disponible_desde_fecha=f_src.disponible_desde_fecha,
#         disponible_hasta_fecha=f_src.disponible_hasta_fecha,
#         estado=f_src.estado,
#         forma_envio=f_src.forma_envio,
#         es_publico=f_src.es_publico,
#         auto_envio=f_src.auto_envio,
#     )

#     # 3) última versión del original
#     ver_src = (FormularioIndexVersion.objects
#                .filter(formulario_id=f_src)
#                .order_by("-fecha_creacion")
#                .first())

#     # si no hay versiones/páginas, devolvemos el clon vacío
#     if not ver_src:
#         return {"formulario_id": str(f_dst.id), "paginas": []}

#     # 4) nueva versión para el clon
#     ver_dst = FormularioIndexVersion.objects.create(
#         id_index_version=uuid.uuid4(),
#         formulario_id=f_dst
#     )

#     # 5) clonar páginas de esa versión
#     paginas_src = (Pagina.objects
#                    .filter(index_version=ver_src, formulario_id=f_src)
#                    .order_by("secuencia"))

#     result_paginas = []

#     for p in paginas_src:
#         # 5.1 nueva página en el clon
#         p_new = Pagina.objects.create(
#             id_pagina=uuid.uuid4(),
#             index_version=ver_dst,
#             formulario_id=f_dst,
#             secuencia=p.secuencia,
#             nombre=p.nombre,
#             descripcion=p.descripcion,
#         )
#         result_paginas.append({"old": str(p.id_pagina), "new": str(p_new.id_pagina)})

#         # 5.2 última versión de la página original
#         p_src_32 = _uuid32_no_dashes(str(p.id_pagina))
#         pv_src = (PaginaVersion.objects
#                   .filter(id_pagina=p_src_32)
#                   .order_by("-fecha_creacion")
#                   .first())

#         # 5.3 crear versión para la nueva página
#         pv_dst = PaginaVersion.objects.create(
#             id_pagina_version=_uuid32_no_dashes(str(uuid.uuid4())),
#             fecha_creacion=pv_src.fecha_creacion if pv_src else timezone.now(),
#             id_pagina=_uuid32_no_dashes(str(p_new.id_pagina)),
#         )

#         # 5.4 copiar enlaces de campos (solo ORM)
#         if pv_src:
#             links = list(PaginaCampo.objects
#                          .select_related("id_campo")
#                          .filter(id_pagina_version=pv_src)
#                          .order_by("sequence"))

#             nuevos = [
#                 PaginaCampo(
#                     id_campo=lnk.id_campo,                # FK a Campo (Char(32) pk)
#                     id_pagina_version=pv_dst,             # FK a PaginaVersion
#                     sequence=lnk.sequence,
#                 )
#                 for lnk in links
#             ]
#             if nuevos:
#                 PaginaCampo.objects.bulk_create(nuevos)

#     return {"formulario_id": str(f_dst.id), "paginas": result_paginas}
