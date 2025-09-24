# # services.py
# from typing import Dict, Optional
# from django.db import connection, transaction
# from django.core.exceptions import ObjectDoesNotExist, ValidationError
# from .models import Formulario, FormularioActualVersion  
# from django.db import transaction
# from django.db.models import Max, Prefetch
# from django.apps import apps
# from django.utils import timezone
# from django.db import models
# from .models import (
#     Formulario, FormularioIndexVersion, Pagina, PaginaIndex, Campo,
#     PaginaActualVersion, PaginaCampoActual
# )

import json
import uuid
from django.db import transaction, connection

from django.apps import apps
from typing import Dict, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
import re

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
        for p in Pagina.objects.filter(index_version=nueva_version):
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
      - clona PaginaCampo de la última versión
      - inserta el nuevo Campo en PaginaCampo (al final o sequence pedido)
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

    # 3) Clonar mapeo campo↔pagina_version de la última, si existe
    max_seq = 0
    if prev_pv:
        rows = list(
            PaginaCampo.objects
            .filter(id_pagina_version=prev_pv)
            .order_by("sequence")
            .values("id_campo", "sequence")
        )
        if rows:
            objs = [
                PaginaCampo(
                    id_campo_id=row["id_campo"],
                    id_pagina_version=nueva_pv,
                    sequence=row["sequence"],
                )
                for row in rows
            ]
            PaginaCampo.objects.bulk_create(objs)
            max_seq = rows[-1]["sequence"] or 0

    # 4) Insertar el NUEVO campo en la nueva PaginaVersion
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

def _pagina_version_actual_o_nueva(id_pagina: str) -> PaginaVersion:
    id_pagina_32 = _uuid32_no_dashes(id_pagina)

    pv = (PaginaVersion.objects
          .filter(id_pagina=id_pagina_32)
          .order_by("-fecha_creacion")
          .first())
    if pv:
        return pv

    nuevo_id = _uuid32()  # ya devuelve 32 sin guiones
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.formularios_pagina_version (id_pagina_version, fecha_creacion, id_pagina)
            VALUES (%s, SYSUTCDATETIME(), %s)
            """,
            [nuevo_id, id_pagina_32],
        )
    return PaginaVersion(id_pagina_version=nuevo_id, id_pagina=id_pagina_32)

def _siguiente_sequence(id_pagina_version: str) -> int:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT ISNULL(MAX([sequence]), 0) FROM dbo.formularios_pagina_campo WHERE id_pagina_version = %s
            """,
            [id_pagina_version],
        )
        (mx,) = cur.fetchone()
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
        cur.execute(
            """
            INSERT INTO dbo.formularios_pagina_campo (id_campo, id_pagina_version, [sequence])
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
# def _quote(name: str) -> str:
#     return connection.ops.quote_name(name)

# def _table_exists(table: str) -> bool:
#     with connection.cursor() as cur:
#         return table in connection.introspection.table_names()

# def _get_columns(table: str):
#     with connection.cursor() as cur:
#         return [c.name for c in connection.introspection.get_table_description(cur, table)]

# def _list_res_tables(prefix: str = "res_"):
#     with connection.cursor() as cur:
#         tables = connection.introspection.table_names()
#     return [t for t in tables if t.startswith(prefix)]

# def _get_instancia_table_name() -> Optional[str]:
#     # Si tienes modelo ORM:
#     # return InstanciaFormulario._meta.db_table
#     # Si aún no lo tienes mapeado por ORM, pon el nombre físico:
#     candidate = "instancia_formulario"
#     return candidate if _table_exists(candidate) else None

# def _delete_rows_in_res_tables(formulario_id) -> Dict[str, int]:
#     """
#     Limpia filas en tablas res_* asociadas al formulario.
#     - Preferido: join vía id_instancia -> instancia_formulario(formulario_id)
#     - Plan B: columna directa formulario_id / id_formulario en la tabla hoja
#     """
#     deleted = {}
#     inst_tbl = _get_instancia_table_name()
#     res_tables = _list_res_tables()

#     with connection.cursor() as cur:
#         for t in res_tables:
#             cols = set(_get_columns(t))

#             # 1) vía instancia (si existe la tabla y la columna)
#             id_inst_col = None
#             if "id_instancia_id" in cols:
#                 id_inst_col = "id_instancia_id"
#             elif "id_instancia" in cols:
#                 id_inst_col = "id_instancia"

#             if inst_tbl and id_inst_col:
#                 sql = (
#                     f"DELETE r FROM {_quote(t)} r "
#                     f"INNER JOIN {_quote(inst_tbl)} i "
#                     f"ON r.{_quote(id_inst_col)} = i.{_quote('id_instancia')} "
#                     f"WHERE i.{_quote('id_formulario')} = %s"
#                 )
#                 cur.execute(sql, [str(formulario_id)])
#                 deleted[t] = cur.rowcount
#                 continue

#             # 2) columna directa en la hoja
#             form_col = None
#             if "formulario_id" in cols:
#                 form_col = "formulario_id"
#             elif "id_formulario" in cols:
#                 form_col = "id_formulario"

#             if form_col:
#                 sql = f"DELETE FROM {_quote(t)} WHERE {_quote(form_col)} = %s"
#                 cur.execute(sql, [str(formulario_id)])
#                 deleted[t] = cur.rowcount
#                 continue

#             # 3) no se pudo filtrar
#             deleted[t] = 0

#     return deleted

# @transaction.atomic
# def delete_formulario_hard(formulario_id):
#     """
#     Limpia respuestas en res_* y borra el formulario (cascade del resto).
#     Retorna un resumen.
#     """
#     try:
#         form = (Formulario.objects
#                 .select_for_update()
#                 .get(pk=formulario_id))
#     except ObjectDoesNotExist:
#         return {"ok": False, "error": "Formulario no existe"}

#     hojas = _delete_rows_in_res_tables(formulario_id)
#     form.delete()

#     return {
#         "ok": True,
#         "formulario_id": str(formulario_id),
#         "respuestas_borradas": hojas
#     }

# def _nombre_copia_unico(nombre_base: str, Model):
#     """
#     Genera 'Nombre_Copia', 'Nombre_Copia (2)', 'Nombre_Copia (3)', ...
#     evitando colisiones.
#     """
#     base = f"{nombre_base}_Copia"
#     if not Model.objects.filter(nombre=base).exists():
#         return base
#     n = 2
#     while True:
#         cand = f"{base} ({n})"
#         if not Model.objects.filter(nombre=cand).exists():
#             return cand
#         n += 1

# @transaction.atomic
# def duplicar_formulario(formulario_id):
#     Formulario = apps.get_model("formularios", "Formulario")
#     FormularioIndexVersion = apps.get_model("formularios", "FormularioIndexVersion")
#     Pagina = apps.get_model("formularios", "Pagina")
#     PaginaIndex = apps.get_model("formularios", "PaginaIndex")

#     # 1) formulario origen
#     src = (Formulario.objects
#            .select_related("categoria")
#            .get(pk=formulario_id))

#     # 2) nuevo formulario
#     nuevo_nombre = _nombre_copia_unico(src.nombre, Formulario)
#     dst = Formulario.objects.create(
#         categoria=src.categoria,
#         nombre=nuevo_nombre,
#         descripcion=src.descripcion,
#         permitir_fotos=src.permitir_fotos,
#         permitir_gps=src.permitir_gps,
#         disponible_desde_fecha=src.disponible_desde_fecha,
#         disponible_hasta_fecha=src.disponible_hasta_fecha,
#         estado=src.estado,
#         forma_envio=src.forma_envio,
#         es_publico=src.es_publico,
#         auto_envio=src.auto_envio,
#     )

#     # 3) detectar última versión del origen
#     last_ver = (FormularioIndexVersion.objects
#                 .filter(formulario=src)
#                 .order_by("-fecha_creacion")
#                 .first())

#     if last_ver is None:
#         # no hay páginas/versión previa; crea versión vacía
#         new_ver = FormularioIndexVersion.objects.create(formulario=dst)
#         return {
#             "ok": True,
#             "formulario_nuevo_id": str(dst.id),
#             "version_nueva_id": str(new_ver.id_index_version),
#             "paginas_copiadas": 0
#         }

#     # 4) crear versión destino
#     new_ver = FormularioIndexVersion.objects.create(formulario=dst)

#     # 5) clonar páginas de la última versión (conservando secuencia)
#     paginas_src = (Pagina.objects
#                    .filter(index_version=last_ver)
#                    .order_by("secuencia"))
#     paginas_map = {}  # src_id -> dst_obj

#     for p in paginas_src:
#         p_new = Pagina.objects.create(
#             index_version=new_ver,
#             formulario=dst,
#             secuencia=p.secuencia,
#             nombre=p.nombre,
#             descripcion=p.descripcion,
#         )
#         paginas_map[p.id_pagina] = p_new
#         PaginaIndex.objects.create(
#             id_index_version=new_ver,
#             id_pagina=p_new,
#             id_formulario=dst
#         )

#     return {
#         "ok": True,
#         "formulario_nuevo_id": str(dst.id),
#         "version_nueva_id": str(new_ver.id_index_version),
#         "paginas_copiadas": paginas_src.count(),
#         "nombre": dst.nombre
#     }

# def activar_version(formulario, version):
#     """
#     Apunta el formulario a 'version' como ACTUAL y materializa:
#       - PaginaIndexActual
#       - PaginaCampoActual
#     """
#     from .models import (
#         FormularioActualVersion, PaginaIndex, PaginaActualVersion,
#         PaginaCampoActual, Pagina, Campo
#     )

#     if version.formulario_id != formulario.id:
#         raise ValidationError("La versión no corresponde al formulario.")

#     with transaction.atomic():
#         # 1) puntero a versión vigente
#         fva, _ = FormularioActualVersion.objects.update_or_create(
#             formulario=formulario,
#             defaults={"index_version": version, "publicada_en": timezone.now()},
#         )

#         # 2) reconstruir PaginaIndexActual
#         PaginaActualVersion.objects.filter(formulario=formulario).delete()
#         links = (PaginaIndex.objects
#                  .filter(id_index_version=version)
#                  .select_related("id_pagina"))

#         mapa = {}
#         bulk_pages = []
#         for link in links:
#             bulk_pages.append(PaginaActualVersion(
#                 version_activa=fva,
#                 formulario=formulario,
#                 pagina=link.id_pagina,
#                 # orden=getattr(link, "orden", link.id_pagina.secuencia),
#                 fecha_creacion=link.fecha_creacion,
#             ))
#         created = PaginaActualVersion.objects.bulk_create(bulk_pages)
#         for obj in created:
#             mapa[obj.pagina_id] = obj

#         # 3) reconstruir PaginaCampoActual
#         PaginaCampoActual.objects.filter(pagina_actual__formulario=formulario).delete()
#         bulk_fields = []
#         paginas = (Pagina.objects
#                    .filter(id_pagina__in=mapa.keys())
#                    .prefetch_related(Prefetch("campos", queryset=Campo.objects.all().order_by("sequence","id_campo"))))
#         for p in paginas:
#             pa = mapa[p.id_pagina]
#             for c in p.campos.all():
#                 bulk_fields.append(PaginaCampoActual(
#                     pagina_actual=pa,
#                     campo=c,
#                     orden=c.sequence,
#                     requerido=c.requerido,
#                     config=c.config,
#                 ))
#         if bulk_fields:
#             PaginaCampoActual.objects.bulk_create(bulk_fields)

#     return fva

# def _clonar_paginas_y_campos(src_version, dst_version, formulario):
#     """
#     Clona todas las Páginas de src_version hacia dst_version,
#     incluyendo TODOS los Campos y re-mapeando la relación 'grupo'.
#     """
#     from .models import Pagina, PaginaIndex, Campo  # import local para evitar ciclos

#     paginas_src = (Pagina.objects
#                    .filter(index_version=src_version)
#                    .order_by("secuencia"))

#     for p in paginas_src:
#         # 1) Crear la página destino
#         p_new = Pagina.objects.create(
#             index_version=dst_version,
#             formulario=formulario,
#             secuencia=p.secuencia,
#             nombre=p.nombre,
#             descripcion=p.descripcion,
#         )
#         PaginaIndex.objects.create(
#             id_index_version=dst_version,
#             id_pagina=p_new,
#             id_formulario=formulario
#         )

#         # 2) Clonar campos (dos pasadas para resolver 'grupo')
#         old_to_new = {}
#         campos_src = list(Campo.objects.filter(pagina=p)
#                           .order_by("sequence", "id_campo"))

#         # 2.a crear copias sin grupo
#         for c in campos_src:
#             c_new = Campo.objects.create(
#                 pagina=p_new,
#                 tipo=c.tipo,
#                 clase=c.clase,
#                 nombre_campo=c.nombre_campo,
#                 etiqueta=c.etiqueta,
#                 ayuda=c.ayuda,
#                 config=c.config,      # JSONField ya es serializable
#                 requerido=c.requerido,
#                 sequence=c.sequence,
#                 grupo=None,           # se ajusta en la 2ª pasada
#             )
#             old_to_new[c.id_campo] = c_new

#         # 2.b re-asignar 'grupo' apuntando a los nuevos IDs
#         to_update = []
#         for c in campos_src:
#             if c.grupo_id:
#                 hijo = old_to_new[c.id_campo]
#                 hijo.grupo = old_to_new.get(c.grupo_id)  # puede ser None si no estaba en el set
#                 to_update.append(hijo)
#         if to_update:
#             Campo.objects.bulk_update(to_update, ["grupo"])

# @transaction.atomic
# def _reconstruir_paginas_vigentes_para_version(version: FormularioIndexVersion):
#     """
#     Reconstruye las proyecciones 'vigentes' (PaginaActualVersion / PaginaCampoActual)
#     a partir de una versión concreta.
#     Borra lo 'vigente' actual del formulario y lo reemplaza por lo de 'version'.
#     """
#     form = version.formulario

#     # 1) limpiar proyecciones actuales de ESTE formulario
#     actuales = PaginaActualVersion.objects.filter(formulario=form)
#     PaginaCampoActual.objects.filter(pagina_actual__in=actuales).delete()
#     actuales.delete()

#     # 2) crear nuevas paginas vigentes y sus campos desde la version dada
#     paginas = Pagina.objects.filter(index_version=version).order_by("secuencia", "id_pagina")
#     mapa_pag_actual = {}  # pagina_id -> PaginaActualVersion
#     for p in paginas:
#         pa = PaginaActualVersion.objects.create(
#             formulario=form,
#             version_activa=version,
#             pagina=p
#         )
#         mapa_pag_actual[str(p.id_pagina)] = pa

#     # 3) proyectar campos como vigentes
#     for p in paginas:
#         pa = mapa_pag_actual[str(p.id_pagina)]
#         campos = Campo.objects.filter(pagina=p).order_by("sequence", "id_campo")
#         bulk = [
#             PaginaCampoActual(
#                 pagina_actual=pa,
#                 campo=c,
#                 orden=c.sequence,
#                 requerido=c.requerido,
#                 config=c.config,
#             )
#             for c in campos
#         ]
#         if bulk:
#             PaginaCampoActual.objects.bulk_create(bulk)

#     # 4) (opcional) marcar en Formulario la version activa/fecha
#     if hasattr(form, "version_activa_id"):
#         form.version_activa_id = version.id_index_version
#     if hasattr(form, "publicada_en"):
#         form.publicada_en = timezone.now()
#     form.save(update_fields=[f for f in ["version_activa_id","publicada_en"] if hasattr(form, f)])


# @transaction.atomic
# def crear_campo_bumpeando_version_actual(pagina_id: str, campo_data: dict) -> dict:
#     """
#     Clona la VERSIÓN ACTUAL del formulario dueño de la página 'pagina_id' a una nueva versión,
#     clona todas sus páginas y campos, y en la copia de la página objetivo inserta el nuevo campo.
#     Reconstruye las proyecciones 'vigentes' para apuntar a la NUEVA versión.
#     """
#     # 1) página original + su versión actual y formulario
#     pagina_old = (Pagina.objects
#                   .select_related("index_version", "formulario")
#                   .get(pk=pagina_id))
#     ver_old = pagina_old.index_version
#     form = pagina_old.formulario

#     # 2) crear nueva versión
#     ver_new = FormularioIndexVersion.objects.create(formulario=form)

#     # 3) clonar páginas de ver_old -> ver_new
#     page_map = {}
#     paginas_old = (Pagina.objects
#                    .filter(index_version=ver_old)
#                    .order_by("secuencia", "id_pagina"))
#     for p in paginas_old:
#         p_new = Pagina.objects.create(
#             index_version=ver_new,
#             formulario=form,
#             secuencia=p.secuencia,
#             nombre=p.nombre,
#             descripcion=p.descripcion,
#         )
#         PaginaIndex.objects.create(
#             id_index_version=ver_new,
#             id_pagina=p_new,
#             id_formulario=form
#         )
#         page_map[str(p.id_pagina)] = p_new

#     # 4) clonar campos (2 pasadas para respetar 'grupo')
#     campo_map = {}

#     # 4.a crear todos sin grupo
#     for p_old in paginas_old:
#         p_new = page_map[str(p_old.id_pagina)]
#         for c in Campo.objects.filter(pagina=p_old).order_by("sequence", "id_campo"):
#             c_new = Campo.objects.create(
#                 pagina=p_new,
#                 tipo=c.tipo,
#                 clase=c.clase,
#                 nombre_campo=c.nombre_campo,
#                 etiqueta=c.etiqueta,
#                 ayuda=c.ayuda,
#                 config=c.config,
#                 requerido=c.requerido,
#                 sequence=c.sequence,
#                 grupo=None,
#             )
#             campo_map[str(c.id_campo)] = c_new

#     # 4.b reestablecer grupo en los clonados
#     for p_old in paginas_old:
#         for c in Campo.objects.filter(pagina=p_old).only("id_campo","grupo_id"):
#             if c.grupo_id:
#                 nuevo = campo_map[str(c.id_campo)]
#                 nuevo.grupo = campo_map.get(str(c.grupo_id))
#                 nuevo.save(update_fields=["grupo"])

#     # 5) crear el NUEVO campo en la copia de la página objetivo
#     pagina_new = page_map[str(pagina_old.id_pagina)]

#     # remap de grupo si vino referenciando un campo viejo
#     grupo_old = campo_data.get("grupo")
#     if grupo_old:
#         old_id = str(getattr(grupo_old, "id_campo", grupo_old))
#         campo_data = {**campo_data, "grupo": campo_map.get(old_id)}

#     # sequence al final si no viene
#     if not campo_data.get("sequence"):
#         mx = (Campo.objects
#               .filter(pagina=pagina_new)
#               .aggregate(mx=models.Max("sequence"))
#               .get("mx") or 0)
#         campo_data = {**campo_data, "sequence": mx + 1}

#     campo_new = Campo.objects.create(pagina=pagina_new, **campo_data)

#     # 6) reconstruir proyecciones VIGENTES para la nueva versión
#     _reconstruir_paginas_vigentes_para_version(ver_new)

#     return {
#         "ok": True,
#         "version_nueva_id": ver_new.id_index_version,
#         "pagina_nueva_id": pagina_new.id_pagina,
#         "campo": campo_new,
#     }

# @transaction.atomic
# def publicar_nueva_version_por_cambio_en_pagina(pagina: Pagina, nuevo_campo_data: dict):
#     """
#     Crea una NUEVA versión del formulario del que 'pagina' forma parte,
#     manteniendo el MISMO id_pagina para todas las páginas.
#     - Reindexa PaginaIndex hacia la nueva versión (mismas páginas)
#     - Copia los PaginaCampoActual de la versión vigente → a la nueva
#     - Inserta el nuevo Campo SOLO en la nueva versión
#     - Activa la versión
#     """
#     formulario = pagina.formulario

#     # 1) Versión índice nueva
#     ver_idx_nueva = FormularioIndexVersion.objects.create(formulario=formulario)

#     # 2) Reindexar todas las páginas VIGENTES hacia la nueva versión (mismos ids)
#     #    Obtenemos las páginas vigentes desde la versión ACTUAL publicada
#     fva = (FormularioActualVersion.objects
#            .filter(formulario=formulario)
#            .order_by("-publicada_en")
#            .first())

#     if not fva:
#         raise ValueError("El formulario no tiene versión ACTUAL publicada.")

#     paginas_vigentes = (PaginaActualVersion.objects
#                         .select_related("pagina")
#                         .filter(formulario=formulario, version_activa=fva))

#     # Crear PaginaIndex para **las mismas** páginas (id_pagina estable)
#     PaginaIndex.objects.bulk_create([
#         PaginaIndex(
#             id_index_version=ver_idx_nueva,
#             id_pagina=pav.pagina,          # MISMO id_pagina
#             id_formulario=formulario
#         )
#         for pav in paginas_vigentes
#     ])

#     # 3) Materializar PaginaActualVersion para la nueva versión
#     #    (opción A) dejar que 'activar_version' las reconstruya
#     #    (opción B) crearlas aquí. Preferimos A para no duplicar lógica.
#     #    Así que de momento solo preparamos los datos de campos vigentes.

#     # 4) Copiar campos vigentes → nueva versión (cuando se active)
#     #    Creamos un snapshot de qué campos tiene cada página vigente hoy.
#     campos_por_pagina = {
#         pav.pagina_id: list(
#             PaginaCampoActual.objects
#             .filter(pagina_actual=pav)
#             .order_by("orden")
#             .values_list("campo_id", flat=True)
#         )
#         for pav in paginas_vigentes
#     }

#     # 5) Crear el nuevo Campo en la MISMA página estable
#     data = dict(nuevo_campo_data)
#     data.pop("pagina", None)  # forzamos a usar 'pagina' estable
#     # sequence por defecto al final del conjunto ACTUAL de esa página
#     last_seq = (Campo.objects.filter(pagina=pagina)
#                 .aggregate(mx=models.Max("sequence")).get("mx") or 0)
#     data.setdefault("sequence", last_seq + 1)

#     campo_nuevo = Campo.objects.create(pagina=pagina, **data)

#     # 6) Activar la versión (esto materializa PaginaActualVersion y PaginaCampoActual)
#     from .services import activar_version  # si está en el mismo archivo, omite este import
#     activar_version(formulario, ver_idx_nueva)

#     # 7) Agregar los PaginaCampoActual para la nueva versión:
#     #    - reconstruimos el mapeo: pagina_id -> PaginaActualVersion (de la NUEVA versión)
#     pav_nueva_por_pagina = {
#         pav.pagina_id: pav
#         for pav in PaginaActualVersion.objects
#                        .filter(formulario=formulario, version_activa__index_version=ver_idx_nueva)
#     }

#     #    - replicamos los campos que tenía cada página en la versión anterior
#     pca_crear = []
#     for pagina_id, campo_ids in campos_por_pagina.items():
#         pav_new = pav_nueva_por_pagina.get(pagina_id)
#         if not pav_new:
#             continue
#         for i, cid in enumerate(campo_ids, start=1):
#             pca_crear.append(PaginaCampoActual(
#                 pagina_actual=pav_new,
#                 campo_id=cid,
#                 orden=i,
#                 requerido=Campo.objects.get(pk=cid).requerido,
#                 config=Campo.objects.get(pk=cid).config,
#             ))

#     #    - y en la página objetivo, agregamos TAMBIÉN el campo nuevo al final
#     pav_target_new = pav_nueva_por_pagina[pagina.id_pagina]
#     pca_crear.append(PaginaCampoActual(
#         pagina_actual=pav_target_new,
#         campo=campo_nuevo,
#         orden=len(campos_por_pagina.get(pagina.id_pagina, [])) + 1,
#         requerido=campo_nuevo.requerido,
#         config=campo_nuevo.config,
#     ))

#     PaginaCampoActual.objects.bulk_create(pca_crear)

#     return ver_idx_nueva, pav_target_new.pagina, campo_nuevo