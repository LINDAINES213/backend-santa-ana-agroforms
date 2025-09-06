# services.py
from typing import Dict, Optional
from django.db import connection, transaction
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from .models import Formulario  
from django.db import transaction
from django.db.models import Max, Prefetch
from django.apps import apps
from django.utils import timezone

def _quote(name: str) -> str:
    return connection.ops.quote_name(name)

def _table_exists(table: str) -> bool:
    with connection.cursor() as cur:
        return table in connection.introspection.table_names()

def _get_columns(table: str):
    with connection.cursor() as cur:
        return [c.name for c in connection.introspection.get_table_description(cur, table)]

def _list_res_tables(prefix: str = "res_"):
    with connection.cursor() as cur:
        tables = connection.introspection.table_names()
    return [t for t in tables if t.startswith(prefix)]

def _get_instancia_table_name() -> Optional[str]:
    # Si tienes modelo ORM:
    # return InstanciaFormulario._meta.db_table
    # Si aún no lo tienes mapeado por ORM, pon el nombre físico:
    candidate = "instancia_formulario"
    return candidate if _table_exists(candidate) else None

def _delete_rows_in_res_tables(formulario_id) -> Dict[str, int]:
    """
    Limpia filas en tablas res_* asociadas al formulario.
    - Preferido: join vía id_instancia -> instancia_formulario(formulario_id)
    - Plan B: columna directa formulario_id / id_formulario en la tabla hoja
    """
    deleted = {}
    inst_tbl = _get_instancia_table_name()
    res_tables = _list_res_tables()

    with connection.cursor() as cur:
        for t in res_tables:
            cols = set(_get_columns(t))

            # 1) vía instancia (si existe la tabla y la columna)
            id_inst_col = None
            if "id_instancia_id" in cols:
                id_inst_col = "id_instancia_id"
            elif "id_instancia" in cols:
                id_inst_col = "id_instancia"

            if inst_tbl and id_inst_col:
                sql = (
                    f"DELETE r FROM {_quote(t)} r "
                    f"INNER JOIN {_quote(inst_tbl)} i "
                    f"ON r.{_quote(id_inst_col)} = i.{_quote('id_instancia')} "
                    f"WHERE i.{_quote('id_formulario')} = %s"
                )
                cur.execute(sql, [str(formulario_id)])
                deleted[t] = cur.rowcount
                continue

            # 2) columna directa en la hoja
            form_col = None
            if "formulario_id" in cols:
                form_col = "formulario_id"
            elif "id_formulario" in cols:
                form_col = "id_formulario"

            if form_col:
                sql = f"DELETE FROM {_quote(t)} WHERE {_quote(form_col)} = %s"
                cur.execute(sql, [str(formulario_id)])
                deleted[t] = cur.rowcount
                continue

            # 3) no se pudo filtrar
            deleted[t] = 0

    return deleted

@transaction.atomic
def delete_formulario_hard(formulario_id):
    """
    Limpia respuestas en res_* y borra el formulario (cascade del resto).
    Retorna un resumen.
    """
    try:
        form = (Formulario.objects
                .select_for_update()
                .get(pk=formulario_id))
    except ObjectDoesNotExist:
        return {"ok": False, "error": "Formulario no existe"}

    hojas = _delete_rows_in_res_tables(formulario_id)
    form.delete()

    return {
        "ok": True,
        "formulario_id": str(formulario_id),
        "respuestas_borradas": hojas
    }

def _nombre_copia_unico(nombre_base: str, Model):
    """
    Genera 'Nombre_Copia', 'Nombre_Copia (2)', 'Nombre_Copia (3)', ...
    evitando colisiones.
    """
    base = f"{nombre_base}_Copia"
    if not Model.objects.filter(nombre=base).exists():
        return base
    n = 2
    while True:
        cand = f"{base} ({n})"
        if not Model.objects.filter(nombre=cand).exists():
            return cand
        n += 1

@transaction.atomic
def duplicar_formulario(formulario_id):
    Formulario = apps.get_model("formularios", "Formulario")
    FormularioIndexVersion = apps.get_model("formularios", "FormularioIndexVersion")
    Pagina = apps.get_model("formularios", "Pagina")
    PaginaIndex = apps.get_model("formularios", "PaginaIndex")

    # 1) formulario origen
    src = (Formulario.objects
           .select_related("categoria")
           .get(pk=formulario_id))

    # 2) nuevo formulario
    nuevo_nombre = _nombre_copia_unico(src.nombre, Formulario)
    dst = Formulario.objects.create(
        categoria=src.categoria,
        nombre=nuevo_nombre,
        descripcion=src.descripcion,
        permitir_fotos=src.permitir_fotos,
        permitir_gps=src.permitir_gps,
        disponible_desde_fecha=src.disponible_desde_fecha,
        disponible_hasta_fecha=src.disponible_hasta_fecha,
        estado=src.estado,
        forma_envio=src.forma_envio,
        es_publico=src.es_publico,
        auto_envio=src.auto_envio,
    )

    # 3) detectar última versión del origen
    last_ver = (FormularioIndexVersion.objects
                .filter(formulario=src)
                .order_by("-fecha_creacion")
                .first())

    if last_ver is None:
        # no hay páginas/versión previa; crea versión vacía
        new_ver = FormularioIndexVersion.objects.create(formulario=dst)
        return {
            "ok": True,
            "formulario_nuevo_id": str(dst.id),
            "version_nueva_id": str(new_ver.id_index_version),
            "paginas_copiadas": 0
        }

    # 4) crear versión destino
    new_ver = FormularioIndexVersion.objects.create(formulario=dst)

    # 5) clonar páginas de la última versión (conservando secuencia)
    paginas_src = (Pagina.objects
                   .filter(index_version=last_ver)
                   .order_by("secuencia"))
    paginas_map = {}  # src_id -> dst_obj

    for p in paginas_src:
        p_new = Pagina.objects.create(
            index_version=new_ver,
            formulario=dst,
            secuencia=p.secuencia,
            nombre=p.nombre,
            descripcion=p.descripcion,
        )
        paginas_map[p.id_pagina] = p_new
        PaginaIndex.objects.create(
            id_index_version=new_ver,
            id_pagina=p_new,
            id_formulario=dst
        )

    return {
        "ok": True,
        "formulario_nuevo_id": str(dst.id),
        "version_nueva_id": str(new_ver.id_index_version),
        "paginas_copiadas": paginas_src.count(),
        "nombre": dst.nombre
    }

def activar_version(formulario, version):
    """
    Apunta el formulario a 'version' como ACTUAL y materializa:
      - PaginaIndexActual
      - PaginaCampoActual
    """
    from .models import (
        FormularioActualVersion, PaginaIndex, PaginaActualVersion,
        PaginaCampoActual, Pagina, Campo
    )

    if version.formulario_id != formulario.id:
        raise ValidationError("La versión no corresponde al formulario.")

    with transaction.atomic():
        # 1) puntero a versión vigente
        fva, _ = FormularioActualVersion.objects.update_or_create(
            formulario=formulario,
            defaults={"index_version": version, "publicada_en": timezone.now()},
        )

        # 2) reconstruir PaginaIndexActual
        PaginaActualVersion.objects.filter(formulario=formulario).delete()
        links = (PaginaIndex.objects
                 .filter(id_index_version=version)
                 .select_related("id_pagina"))

        mapa = {}
        bulk_pages = []
        for link in links:
            bulk_pages.append(PaginaActualVersion(
                version_activa=fva,
                formulario=formulario,
                pagina=link.id_pagina,
                # orden=getattr(link, "orden", link.id_pagina.secuencia),
                fecha_creacion=link.fecha_creacion,
            ))
        created = PaginaActualVersion.objects.bulk_create(bulk_pages)
        for obj in created:
            mapa[obj.pagina_id] = obj

        # 3) reconstruir PaginaCampoActual
        PaginaCampoActual.objects.filter(pagina_actual__formulario=formulario).delete()
        bulk_fields = []
        paginas = (Pagina.objects
                   .filter(id_pagina__in=mapa.keys())
                   .prefetch_related(Prefetch("campos", queryset=Campo.objects.all().order_by("sequence","id_campo"))))
        for p in paginas:
            pa = mapa[p.id_pagina]
            for c in p.campos.all():
                bulk_fields.append(PaginaCampoActual(
                    pagina_actual=pa,
                    campo=c,
                    orden=c.sequence,
                    requerido=c.requerido,
                    config=c.config,
                ))
        if bulk_fields:
            PaginaCampoActual.objects.bulk_create(bulk_fields)

    return fva