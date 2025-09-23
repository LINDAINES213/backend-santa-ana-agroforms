# services.py
from typing import Dict, Optional
from django.db import connection, transaction
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from .models import Formulario, FormularioActualVersion  
from django.db import transaction
from django.db.models import Max, Prefetch
from django.apps import apps
from django.utils import timezone
from django.db import models
from .models import (
    Formulario, FormularioIndexVersion, Pagina, PaginaIndex, Campo,
    PaginaActualVersion, PaginaCampoActual
)


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

def _clonar_paginas_y_campos(src_version, dst_version, formulario):
    """
    Clona todas las Páginas de src_version hacia dst_version,
    incluyendo TODOS los Campos y re-mapeando la relación 'grupo'.
    """
    from .models import Pagina, PaginaIndex, Campo  # import local para evitar ciclos

    paginas_src = (Pagina.objects
                   .filter(index_version=src_version)
                   .order_by("secuencia"))

    for p in paginas_src:
        # 1) Crear la página destino
        p_new = Pagina.objects.create(
            index_version=dst_version,
            formulario=formulario,
            secuencia=p.secuencia,
            nombre=p.nombre,
            descripcion=p.descripcion,
        )
        PaginaIndex.objects.create(
            id_index_version=dst_version,
            id_pagina=p_new,
            id_formulario=formulario
        )

        # 2) Clonar campos (dos pasadas para resolver 'grupo')
        old_to_new = {}
        campos_src = list(Campo.objects.filter(pagina=p)
                          .order_by("sequence", "id_campo"))

        # 2.a crear copias sin grupo
        for c in campos_src:
            c_new = Campo.objects.create(
                pagina=p_new,
                tipo=c.tipo,
                clase=c.clase,
                nombre_campo=c.nombre_campo,
                etiqueta=c.etiqueta,
                ayuda=c.ayuda,
                config=c.config,      # JSONField ya es serializable
                requerido=c.requerido,
                sequence=c.sequence,
                grupo=None,           # se ajusta en la 2ª pasada
            )
            old_to_new[c.id_campo] = c_new

        # 2.b re-asignar 'grupo' apuntando a los nuevos IDs
        to_update = []
        for c in campos_src:
            if c.grupo_id:
                hijo = old_to_new[c.id_campo]
                hijo.grupo = old_to_new.get(c.grupo_id)  # puede ser None si no estaba en el set
                to_update.append(hijo)
        if to_update:
            Campo.objects.bulk_update(to_update, ["grupo"])

@transaction.atomic
def _reconstruir_paginas_vigentes_para_version(version: FormularioIndexVersion):
    """
    Reconstruye las proyecciones 'vigentes' (PaginaActualVersion / PaginaCampoActual)
    a partir de una versión concreta.
    Borra lo 'vigente' actual del formulario y lo reemplaza por lo de 'version'.
    """
    form = version.formulario

    # 1) limpiar proyecciones actuales de ESTE formulario
    actuales = PaginaActualVersion.objects.filter(formulario=form)
    PaginaCampoActual.objects.filter(pagina_actual__in=actuales).delete()
    actuales.delete()

    # 2) crear nuevas paginas vigentes y sus campos desde la version dada
    paginas = Pagina.objects.filter(index_version=version).order_by("secuencia", "id_pagina")
    mapa_pag_actual = {}  # pagina_id -> PaginaActualVersion
    for p in paginas:
        pa = PaginaActualVersion.objects.create(
            formulario=form,
            version_activa=version,
            pagina=p
        )
        mapa_pag_actual[str(p.id_pagina)] = pa

    # 3) proyectar campos como vigentes
    for p in paginas:
        pa = mapa_pag_actual[str(p.id_pagina)]
        campos = Campo.objects.filter(pagina=p).order_by("sequence", "id_campo")
        bulk = [
            PaginaCampoActual(
                pagina_actual=pa,
                campo=c,
                orden=c.sequence,
                requerido=c.requerido,
                config=c.config,
            )
            for c in campos
        ]
        if bulk:
            PaginaCampoActual.objects.bulk_create(bulk)

    # 4) (opcional) marcar en Formulario la version activa/fecha
    if hasattr(form, "version_activa_id"):
        form.version_activa_id = version.id_index_version
    if hasattr(form, "publicada_en"):
        form.publicada_en = timezone.now()
    form.save(update_fields=[f for f in ["version_activa_id","publicada_en"] if hasattr(form, f)])


@transaction.atomic
def crear_campo_bumpeando_version_actual(pagina_id: str, campo_data: dict) -> dict:
    """
    Clona la VERSIÓN ACTUAL del formulario dueño de la página 'pagina_id' a una nueva versión,
    clona todas sus páginas y campos, y en la copia de la página objetivo inserta el nuevo campo.
    Reconstruye las proyecciones 'vigentes' para apuntar a la NUEVA versión.
    """
    # 1) página original + su versión actual y formulario
    pagina_old = (Pagina.objects
                  .select_related("index_version", "formulario")
                  .get(pk=pagina_id))
    ver_old = pagina_old.index_version
    form = pagina_old.formulario

    # 2) crear nueva versión
    ver_new = FormularioIndexVersion.objects.create(formulario=form)

    # 3) clonar páginas de ver_old -> ver_new
    page_map = {}
    paginas_old = (Pagina.objects
                   .filter(index_version=ver_old)
                   .order_by("secuencia", "id_pagina"))
    for p in paginas_old:
        p_new = Pagina.objects.create(
            index_version=ver_new,
            formulario=form,
            secuencia=p.secuencia,
            nombre=p.nombre,
            descripcion=p.descripcion,
        )
        PaginaIndex.objects.create(
            id_index_version=ver_new,
            id_pagina=p_new,
            id_formulario=form
        )
        page_map[str(p.id_pagina)] = p_new

    # 4) clonar campos (2 pasadas para respetar 'grupo')
    campo_map = {}

    # 4.a crear todos sin grupo
    for p_old in paginas_old:
        p_new = page_map[str(p_old.id_pagina)]
        for c in Campo.objects.filter(pagina=p_old).order_by("sequence", "id_campo"):
            c_new = Campo.objects.create(
                pagina=p_new,
                tipo=c.tipo,
                clase=c.clase,
                nombre_campo=c.nombre_campo,
                etiqueta=c.etiqueta,
                ayuda=c.ayuda,
                config=c.config,
                requerido=c.requerido,
                sequence=c.sequence,
                grupo=None,
            )
            campo_map[str(c.id_campo)] = c_new

    # 4.b reestablecer grupo en los clonados
    for p_old in paginas_old:
        for c in Campo.objects.filter(pagina=p_old).only("id_campo","grupo_id"):
            if c.grupo_id:
                nuevo = campo_map[str(c.id_campo)]
                nuevo.grupo = campo_map.get(str(c.grupo_id))
                nuevo.save(update_fields=["grupo"])

    # 5) crear el NUEVO campo en la copia de la página objetivo
    pagina_new = page_map[str(pagina_old.id_pagina)]

    # remap de grupo si vino referenciando un campo viejo
    grupo_old = campo_data.get("grupo")
    if grupo_old:
        old_id = str(getattr(grupo_old, "id_campo", grupo_old))
        campo_data = {**campo_data, "grupo": campo_map.get(old_id)}

    # sequence al final si no viene
    if not campo_data.get("sequence"):
        mx = (Campo.objects
              .filter(pagina=pagina_new)
              .aggregate(mx=models.Max("sequence"))
              .get("mx") or 0)
        campo_data = {**campo_data, "sequence": mx + 1}

    campo_new = Campo.objects.create(pagina=pagina_new, **campo_data)

    # 6) reconstruir proyecciones VIGENTES para la nueva versión
    _reconstruir_paginas_vigentes_para_version(ver_new)

    return {
        "ok": True,
        "version_nueva_id": ver_new.id_index_version,
        "pagina_nueva_id": pagina_new.id_pagina,
        "campo": campo_new,
    }

@transaction.atomic
def publicar_nueva_version_por_cambio_en_pagina(pagina_actual: PaginaActualVersion, nuevo_campo_data: dict):
    formulario = pagina_actual.formulario

    # 1) Crear versión índice nueva
    ver_idx_nueva = FormularioIndexVersion.objects.create(formulario=formulario)

    # 2) Clonar todas las páginas VIGENTES → nueva versión (y registrar PaginaIndex)
    old2new_page = {}
    paginas_actuales = (PaginaActualVersion.objects
                        .select_related("pagina")
                        .filter(formulario=formulario)
                        .order_by("pagina__secuencia", "pagina_id"))

    for pa in paginas_actuales:
        p_old = pa.pagina
        p_new = Pagina.objects.create(
            index_version=ver_idx_nueva,
            formulario=formulario,
            secuencia=p_old.secuencia,
            nombre=p_old.nombre,
            descripcion=p_old.descripcion,
        )
        PaginaIndex.objects.create(
            id_index_version=ver_idx_nueva,
            id_pagina=p_new,
            id_formulario=formulario
        )
        old2new_page[str(p_old.id_pagina)] = p_new

    # 3) Clonar CAMPOS en dos pasadas (remapeando 'grupo')
    campo_old2new = {}
    for pa in paginas_actuales:
        p_old = pa.pagina
        p_new = old2new_page[str(p_old.id_pagina)]
        campos_old = list(Campo.objects.filter(pagina=p_old).order_by("sequence", "id_campo"))

        # 3.a primera pasada: crear sin grupo
        clones = []
        for c in campos_old:
            clones.append(Campo(
                pagina=p_new,
                tipo=c.tipo,
                clase=c.clase,
                nombre_campo=c.nombre_campo,
                etiqueta=c.etiqueta,
                ayuda=c.ayuda,
                config=c.config,
                requerido=c.requerido,
                sequence=c.sequence,
                grupo=None,
            ))
        created = Campo.objects.bulk_create(clones)
        for c_old, c_new in zip(campos_old, created):
            campo_old2new[str(c_old.id_campo)] = c_new

        # 3.b segunda pasada: setear grupo remapeado
        to_update = []
        for c_old in campos_old:
            if c_old.grupo_id:
                c_new = campo_old2new[str(c_old.id_campo)]
                c_new.grupo = campo_old2new.get(str(c_old.grupo_id))
                to_update.append(c_new)
        if to_update:
            Campo.objects.bulk_update(to_update, ["grupo"])

    # 4) Insertar el NUEVO campo en la página clonada objetivo
    p_target_new = old2new_page[str(pagina_actual.pagina_id)]
    data = dict(nuevo_campo_data)

    # remapeo de grupo si el payload refería un campo viejo
    if data.get("grupo"):
        g = data["grupo"]
        old_id = str(getattr(g, "id_campo", g))
        data["grupo"] = campo_old2new.get(old_id)

    # sequence por defecto al final
    if not data.get("sequence"):
        last = (Campo.objects.filter(pagina=p_target_new)
                .aggregate(mx=models.Max("sequence")).get("mx") or 0)
        data["sequence"] = last + 1

    campo_creado = Campo.objects.create(pagina=p_target_new, **data)

    # 5) Activar la versión para materializar *_Actual
    from .services import activar_version
    activar_version(formulario, ver_idx_nueva)

    # Devuelve objetos útiles
    return ver_idx_nueva, p_target_new, campo_creado