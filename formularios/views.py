from formularios.exports import content_bytes_para_un_form, excel_bytes_para_un_form, zip_bytes_todos_los_forms
from .services import _uuid32, _uuid32_no_dashes, crear_campo_en_pagina
from rest_framework import status, filters, viewsets
from rest_framework.decorators import action
from django.db import transaction
from rest_framework.response import Response
from django.db import models
from .models import Campo, CampoGrupo, Categoria, Formulario, Formulario_Index_Version, FormularioEntry, FormularioIndexVersion, FuenteDatosValor, Grupo, Pagina, Pagina_Index_Version, PaginaCampo, PaginaVersion, UserFormulario, Usuario
from .serializers import AsignacionBulkSerializer, CampoSerializer, CampoUpdateSerializer, CategoriaSerializer, CrearCampoEnPaginaSerializer, FormularioListSerializer, FormularioLiteSerializer, FormularioSerializer, FormularioUpdateSerializer, PaginaConCamposSerializer, PaginaSerializer, PaginaUpdateSerializer, UserFormularioSerializer, UsuarioCreateSerializer, UsuarioDetalleSerializer, GrupoSerializer, UsuarioLiteSerializer, UsuarioUpdateSerializer
from django.http import HttpResponse
from django.utils import timezone
import uuid
from django.db.models import Q, Count
from .azure_storage import AzureBlobStorageService
from .models import FuenteDatos
from .serializers import FuenteDatosSerializer, FuenteDatosCreateSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from . import services
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample, OpenApiParameter

from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers, viewsets


@extend_schema_view(
    list=extend_schema(tags=["Datasets"]),
    retrieve=extend_schema(tags=["Datasets"]),
    create=extend_schema(tags=["Datasets"]),
    destroy=extend_schema(tags=["Datasets"]),
)
class FuenteDatosViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "delete", "head", "options"]
    """
    ViewSet para gestionar Fuentes de Datos (Excel/CSV en Azure Blob Storage)
    
    POST /api/fuentes-datos/           - Subir nuevo archivo
    GET  /api/fuentes-datos/           - Listar todas las fuentes
    GET  /api/fuentes-datos/{id}/      - Detalle de una fuente
    PUT  /api/fuentes-datos/{id}/      - Actualizar metadatos (no archivo)
    DELETE /api/fuentes-datos/{id}/    - Eliminar fuente y archivo
    POST /api/fuentes-datos/{id}/preview/ - Re-generar preview
    GET  /api/fuentes-datos/{id}/download/ - Descargar archivo original
    """
    queryset = FuenteDatos.objects.all()
    serializer_class = FuenteDatosSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        if self.action == 'create':
            return FuenteDatosCreateSerializer
        return FuenteDatosSerializer
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        fuente = self.get_object()

        # 0) ¿La fuente está en uso en formularios_fuente_datos_valor?
        en_uso_qs = FuenteDatosValor.objects.filter(fuente=fuente)

        if en_uso_qs.exists():
            # Opcional: devolver lista compacta de campos afectados
            campos = (
                en_uso_qs
                .values("campo__id_campo", "campo__nombre_campo")
                .annotate(usos=Count("id"))
                .order_by("campo__nombre_campo")
            )
            return Response(
                {
                    "detail": "No se puede eliminar: hay campos que utilizan esta fuente.",
                    "campos_en_uso": list(campos),
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 1) Guardamos el blob_name y borramos el registro (cascade limpia los valores)
        blob_name = fuente.blob_name
        response = super().destroy(request, *args, **kwargs)

        # 2) Al confirmar la transacción, eliminamos el blob en Azure
        transaction.on_commit(lambda: AzureBlobStorageService().delete_file(blob_name))

        return response
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Subir archivo a Azure y crear registro"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        archivo = serializer.validated_data['archivo']
        nombre = serializer.validated_data['nombre']
        descripcion = serializer.validated_data.get('descripcion', '')
        
        try:
            file_extension = archivo.name.split('.')[-1]
            azure_service = AzureBlobStorageService()
            
            columnas, preview_data = azure_service.parse_file_preview(
                archivo, file_extension
            )
            
            blob_name, blob_url = azure_service.upload_file(
                archivo, archivo.name
            )
            
            fuente_datos = FuenteDatos.objects.create(
                nombre=nombre,
                descripcion=descripcion,
                archivo_nombre=archivo.name,
                blob_name=blob_name,
                blob_url=blob_url,
                tipo_archivo='excel' if file_extension in ['xlsx', 'xls'] else 'csv',
                columnas=columnas,
                preview_data=preview_data,
                creado_por=request.user if request.user.is_authenticated else None
            )
            
            return Response(
                FuenteDatosSerializer(fuente_datos).data,
                status=status.HTTP_201_CREATED
            )
            
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"detail": f"Error subiendo archivo: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(tags=["Datasets"], summary="Descargar archivo original")
    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """Descargar archivo original desde Azure"""
        fuente_datos = self.get_object()
        
        try:
            azure_service = AzureBlobStorageService()
            file_content = azure_service.download_file(fuente_datos.blob_name)
            
            response = HttpResponse(
                file_content,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                if fuente_datos.tipo_archivo == 'excel' else 'text/csv'
            )
            response['Content-Disposition'] = f'attachment; filename="{fuente_datos.archivo_nombre}"'
            
            return response
        except Exception as e:
            return Response(
                {"detail": f"Error descargando archivo: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(tags=["Datasets"], summary="Regenerar preview")
    @action(detail=True, methods=['post'], url_path='preview')
    def regenerate_preview(self, request, pk=None):
        """Re-generar preview desde Azure (útil si cambió el archivo)"""
        fuente_datos = self.get_object()
        
        try:
            azure_service = AzureBlobStorageService()
            file_content = azure_service.download_file(fuente_datos.blob_name)
            
            from io import BytesIO
            file_obj = BytesIO(file_content)
            
            columnas, preview_data = azure_service.parse_file_preview(
                file_obj,
                fuente_datos.archivo_nombre.split('.')[-1]
            )
            
            fuente_datos.columnas = columnas
            fuente_datos.preview_data = preview_data
            fuente_datos.save()
            
            return Response(
                FuenteDatosSerializer(fuente_datos).data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"detail": f"Error regenerando preview: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

def home(request):
    return HttpResponse("<h1>Bienvenido a la API de Formularios</h1><p>Usa /api/ para acceder a los endpoints.</p>")

@extend_schema_view(
    list=extend_schema(tags=["Categorías"]),
    retrieve=extend_schema(tags=["Categorías"]),
    create=extend_schema(tags=["Categorías"]),
    partial_update=extend_schema(tags=["Categorías"]),
    destroy=extend_schema(tags=["Categorías"]),
)
class CategoriaViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = Categoria.objects.all().order_by("nombre")
    serializer_class = CategoriaSerializer
    lookup_field = "id"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Formulario.objects.filter(categoria=instance).exists():
            return Response(
                {"detail": "No se puede eliminar: hay formularios que usan esta categoría."},
                status=status.HTTP_409_CONFLICT
            )
        return super().destroy(request, *args, **kwargs)

@extend_schema_view(
    list=extend_schema(tags=["Páginas"]),
    retrieve=extend_schema(tags=["Páginas"]),
    create=extend_schema(tags=["Páginas"]),
    partial_update=extend_schema(tags=["Páginas"]),
    destroy=extend_schema(tags=["Páginas"]),
)
class PaginaViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    """
    /api/paginas/                       -> lista páginas
    /api/paginas/{id_pagina}/           -> detalle (agrega ?include_campos=1 para devolver campos)
    /api/paginas/{id_pagina}/campos/    -> GET: solo los campos
    /api/paginas/{id_pagina}/agregar-campo/ -> POST: crear campo en esa página

    """
    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return PaginaUpdateSerializer
        if self.action == "retrieve" and self.request.query_params.get("include_campos") in ("1", "true", "True"):
            return PaginaConCamposSerializer
        return PaginaSerializer

    queryset = Pagina.objects.all().order_by("secuencia")
    serializer_class = PaginaSerializer
    lookup_field = "id_pagina"

    def retrieve(self, request, *args, **kwargs):
        if request.query_params.get("include_campos") in ("1", "true", "True"):
            self.serializer_class = PaginaConCamposSerializer
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(tags=["Campos"], summary="Listar campos de la página")
    @action(detail=True, methods=["get"], url_path="campos")
    def campos(self, request, id_pagina=None):
        pagina = self.get_object()
        data = PaginaConCamposSerializer(pagina, context=self.get_serializer_context()).data
        return Response(data.get("campos", []), status=status.HTTP_200_OK)

    @extend_schema(tags=["Campos"], summary="Agregar campo a la página")
    @action(detail=True, methods=["post"], url_path="campos")
    def agregar_campo(self, request, id_pagina=None):
        id32 = _uuid32_no_dashes(str(id_pagina))
        ser = CrearCampoEnPaginaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = crear_campo_en_pagina(id32, ser.validated_data)
            
            gid = request.data.get("grupo")  # <- ÚNICA fuente del grupo
           
            if gid:
                # 1) Verificar que el grupo existe
                try:
                    g = Grupo.objects.get(pk=str(gid))
                except Grupo.DoesNotExist:
                    return Response(
                        {"detail": f"El grupo '{gid}' no existe. Crea primero el campo de clase 'group'."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 2) Enlazar en formularios_campo_grupo
                campo_id = out.get("id_campo") or out.get("campo_id")
                if not campo_id:
                    return Response({"detail": "No se pudo resolver id_campo creado."}, status=500)

                CampoGrupo.objects.get_or_create(
                    id_grupo=g,
                    id_campo_id=str(campo_id)
                )

            return Response(out, status=status.HTTP_201_CREATED)
        except Exception as e:
            transaction.set_rollback(True)
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        

@extend_schema_view(
    list=extend_schema(tags=["Formularios"]),
    retrieve=extend_schema(tags=["Formularios"]),
)
class FormularioListViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    """
    Este ViewSet devuelve una lista con información más ligera para catálogos.
    """
    queryset = Formulario.objects.all()
    serializer_class = FormularioListSerializer

@extend_schema_view(
    list=extend_schema(tags=["Formularios"]),
    retrieve=extend_schema(tags=["Formularios"]),
    create=extend_schema(tags=["Formularios"]),
    partial_update=extend_schema(tags=["Formularios"]),
    destroy=extend_schema(tags=["Formularios"]),
)
class FormularioViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = Formulario.objects.all()
    serializer_class = FormularioSerializer
    lookup_field = "id"

    def get_serializer_class(self):
        if self.action == "list":
            return FormularioSerializer
        if self.action in ("partial_update", "update"):
            return FormularioUpdateSerializer
        return FormularioSerializer  

    @extend_schema(tags=["Formularios"], summary="Duplicar formulario completo",     
    request=OpenApiTypes.NONE
    )
    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, *args, **kwargs):
        formulario = self.get_object()
        nuevo_nombre = request.data.get("nombre")  
        clon = services.duplicar_formulario(formulario, nuevo_nombre=nuevo_nombre)
        data = FormularioSerializer(clon, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """
        DELETE /api/formularios/{id}/
        Deletes a complete form with all its related data
        """
        
        formulario = self.get_object()
        formulario_id = str(formulario.id)
            
        # 1) ¿Tiene respuestas?
        total = FormularioEntry.objects.filter(form_id=formulario.id).count()
        if total > 0:
            return Response(
                {
                    "detail": "No se puede eliminar: el formulario tiene respuestas en 'formularios_entry'.",
                    "entries_count": total,
                    "hint": "Puede suspenderlo para conservar el histórico y bloquear nuevas respuestas."
                },
                status=status.HTTP_409_CONFLICT
            )
        
        # 2) Sin respuestas → elimina en cascada como ya lo hacías
        try:
            self._delete_formulario_cascade(formulario_id)
            return Response(
                {
                    "detail": f"Formulario {formulario_id} eliminado exitosamente",
                    "deleted_id": formulario_id
                },
                status=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            transaction.set_rollback(True)
            return Response(
                {"detail": f"Error eliminando formulario: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _delete_formulario_cascade(self, formulario_id: str):
        """
        Elimina un formulario y TODA su jerarquía usando el nuevo esquema:
        Formulario -> (historial) Formularios_Index_Version -> Pagina_Index_Version -> Pagina/Versiones/Campos
        """
        with transaction.atomic():
            form = Formulario.objects.get(pk=formulario_id)

            # 1) versiones del formulario (via historial)
            fiv_ids = list(
                Formulario_Index_Version.objects
                .filter(id_formulario=form)
                .values_list("id_index_version", flat=True)
            )

            # 2) páginas del formulario (via punteros a cada versión)
            page_ids = list(
                Pagina_Index_Version.objects
                .filter(id_index_version_id__in=fiv_ids)
                .values_list("id_pagina", flat=True)
            )

            # 3) pagina_version ids (con FK real a Pagina)
            pv_ids = list(
                PaginaVersion.objects
                .filter(id_pagina_id__in=page_ids)
                .values_list("id_pagina_version", flat=True)
            )

            # 4) borrar links campo<->pagina_version
            if pv_ids:
                PaginaCampo.objects.filter(id_pagina_version_id__in=pv_ids).delete()

            # 5) borrar pagina_version
            PaginaVersion.objects.filter(id_pagina_id__in=page_ids).delete()

            # 6) (opcional) borrar campos huérfanos
            Campo.objects.filter(enlaces_pagina__isnull=True).delete()

            # 7) borrar punteros página<->versión y páginas
            if page_ids:
                Pagina_Index_Version.objects.filter(id_pagina_id__in=page_ids).delete()
                Pagina.objects.filter(id_pagina__in=page_ids).delete()

            # 8) borrar historial y versiones
            if fiv_ids:
                Formulario_Index_Version.objects.filter(id_index_version_id__in=fiv_ids).delete()
                FormularioIndexVersion.objects.filter(pk__in=fiv_ids).delete()

            # 9) por último, el formulario
            form.delete()

    @extend_schema(tags=["Páginas"], summary="Agregar nueva página al formulario")
    @action(detail=True, methods=['post'], url_path='agregar-pagina')
    @transaction.atomic
    def agregar_pagina(self, request, *args, **kwargs):
        formulario = self.get_object()
        bump = request.query_params.get("bump", "1") != "0"

        # última versión del formulario por fecha
        link = (Formulario_Index_Version.objects
                .filter(id_formulario=formulario)
                .select_related("id_index_version")
                .order_by("-id_index_version__fecha_creacion")
                .first())

        if link:
            ultima_version = link.id_index_version
        else:
            ultima_version = FormularioIndexVersion.objects.create()
            Formulario_Index_Version.objects.create(id_index_version=ultima_version, id_formulario=formulario)

        version_destino = ultima_version
        if bump:
            version_destino = FormularioIndexVersion.objects.create()
            Formulario_Index_Version.objects.create(id_index_version=version_destino, id_formulario=formulario)
            # mover punteros de TODAS las páginas del form a la nueva versión
            page_ids = (Pagina_Index_Version.objects
                        .filter(id_index_version=ultima_version)
                        .values_list("id_pagina", flat=True))
            for pid in page_ids:
                Pagina_Index_Version.objects.update_or_create(
                    id_pagina_id=pid,
                    defaults={"id_index_version": version_destino},
                )

        # secuencia = max + 1 entre páginas del formulario (en la versión destino)
        last_seq = (Pagina.objects
                    .filter(id_pagina__in=Pagina_Index_Version.objects
                            .filter(id_index_version=version_destino)
                            .values_list("id_pagina", flat=True))
                    .aggregate(max_seq=models.Max("secuencia"))
                    .get("max_seq") or 0)
        secuencia = last_seq + 1

        nueva_pagina = Pagina.objects.create(
            secuencia=secuencia,
            nombre=request.data.get('nombre', 'Nueva página'),
            descripcion=request.data.get('descripcion', ''),
        )

        Pagina_Index_Version.objects.update_or_create(
            id_pagina=nueva_pagina,
            defaults={"id_index_version": version_destino},
        )

        PaginaVersion.objects.create(
            id_pagina_version=_uuid32(),
            id_pagina=nueva_pagina,
            fecha_creacion=timezone.now(),
        )

        return Response({"ok": True, "id_pagina": str(nueva_pagina.id_pagina)}, status=201)

    @extend_schema(tags=["Formularios"], summary="Suspender Formulario")
    @action(detail=True, methods=["post"], url_path="suspender")
    def suspender(self, request, *args, **kwargs):
        form = self.get_object()
        if (form.estado or "").lower() == "suspendida":
            return Response({"detail": "El formulario ya está en estado 'Suspendida'."}, status=200)
        form.estado = "Suspendida"
        form.save(update_fields=["estado"])
        return Response({"ok": True, "id": str(form.id), "estado": form.estado}, status=200)

    @extend_schema(tags=["Formularios"], summary="No permite abrir formularios suspendidos")
    def retrieve(self, request, *args, **kwargs):
        """Bloquear 'abrir' si está Suspendida."""
        obj = self.get_object()
        if (obj.estado or "").lower() == "suspendida":
            return Response(
                {"detail": "Formulario suspendido. Solo puede editar el estado para reactivarlo."},
                status=423  # Locked
            )
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(tags=["Formularios"], summary="Actualizar campo de estado")
    def partial_update(self, request, *args, **kwargs):
        """Si está Suspendida, permitir modificar ÚNICAMENTE el campo 'estado'."""
        obj = self.get_object()
        if (obj.estado or "").lower() == "suspendida":
            campos = set((request.data or {}).keys())
            if campos - {"estado"}:
                return Response(
                    {"detail": "Bloqueado: formulario suspendido. Solo se permite cambiar el estado."},
                    status=423
                )
        return super().partial_update(request, *args, **kwargs)

@extend_schema_view(
    list=extend_schema(tags=["Usuarios"]),
    retrieve=extend_schema(tags=["Usuarios"]),
    create=extend_schema(tags=["Usuarios"]),
    partial_update=extend_schema(tags=["Usuarios"]),
    destroy=extend_schema(tags=["Usuarios"]),
)
class UsuarioViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = Usuario.objects.all().order_by("nombre")
    lookup_field = "nombre_usuario"

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCreateSerializer
        if self.action in ("partial_update", "update"):
            return UsuarioUpdateSerializer
        return UsuarioDetalleSerializer

@extend_schema_view(
    list=extend_schema(tags=["Campos"]),
    retrieve=extend_schema(tags=["Campos"]),
    create=extend_schema(tags=["Campos"]),
    partial_update=extend_schema(tags=["Campos"]),
    destroy=extend_schema(tags=["Campos"]),
)
class CampoViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    """
    GET /api/campos/          -> todos los campos (paginado)
    GET /api/campos/{id}/     -> detalle de un campo
    Filtros:
      ?search=texto           (busca en nombre_campo, etiqueta, clase, tipo)
      ?ordering=nombre_campo  (o -nombre_campo, tipo, clase, etiqueta)
    """
    queryset = Campo.objects.all().order_by("nombre_campo")
    lookup_field = "id_campo"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre_campo", "etiqueta", "clase", "tipo"]
    ordering_fields = ["nombre_campo", "tipo", "clase", "etiqueta"]

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return CampoUpdateSerializer
        return CampoSerializer

@extend_schema_view(
    list=extend_schema(tags=["Grupos"]),
    retrieve=extend_schema(tags=["Grupos"]),
    create=extend_schema(tags=["Grupos"]),
    partial_update=extend_schema(tags=["Grupos"]),
    destroy=extend_schema(tags=["Grupos"]),
)
class GrupoViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = Grupo.objects.all().order_by("nombre")
    serializer_class = GrupoSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        pagina = self.request.query_params.get("pagina")  

        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(id_grupo__icontains=q))

        if pagina:
            try:
                id32 = _uuid32_no_dashes(pagina)
            except Exception:
                return qs.none()
            pv = (PaginaVersion.objects
                  .filter(id_pagina=id32)
                  .order_by("-fecha_creacion")
                  .first())
            if not pv:
                return qs.none()
            campo_group_ids = (PaginaCampo.objects
                               .filter(id_pagina_version=pv.id_pagina_version,
                                       id_campo__clase__iexact="group")
                               .values_list("id_campo", flat=True))
            qs = qs.filter(id_campo_group_id__in=list(campo_group_ids))
        return qs

    @extend_schema(tags=["Grupos"], summary="Listado simple value/label")
    @action(detail=False, methods=["get"], url_path="select")
    def select(self, request):
        qs = self.get_queryset()[:50] 
        return Response([{"value": g.id_grupo, "label": g.nombre} for g in qs])

    @extend_schema(
        tags=["Grupos"], 
        summary="Obtener grupo por id_campo_group",
        parameters=[
            OpenApiParameter(
                name="id_campo_group",
                description="UUID del campo group",
                required=True,
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH
            )
        ],
        responses={
            200: GrupoSerializer,
            404: OpenApiResponse(description="Grupo no encontrado")
        }
    )
    @action(detail=False, methods=["get"], url_path="campo/(?P<id_campo_group>[^/.]+)")
    def by_campo_group(self, request, id_campo_group=None):
        """
        Obtener grupo por id_campo_group
        GET /api/grupos/campo/{id_campo_group}/
        """
        try:
            grupo = Grupo.objects.get(id_campo_group=id_campo_group)
            serializer = self.get_serializer(grupo)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Grupo.DoesNotExist:
            return Response(
                {"detail": "Grupo no encontrado con ese id_campo_group"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"Error: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

@extend_schema_view(
    list=extend_schema(tags=["Asignaciones"]),
    retrieve=extend_schema(tags=["Asignaciones"]),
    create=extend_schema(tags=["Asignaciones"]),
    partial_update=extend_schema(tags=["Asignaciones"]),
    destroy=extend_schema(tags=["Asignaciones"]),
)
class AsignacionViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    """
    Rutas:
      GET    /api/asignaciones/                  -> lista TODAS las asignaciones
      POST   /api/asignaciones/crear-asignacion/              -> asignar a un usuario formularios (dropdown+multiselect)
      GET    /api/asignaciones/opciones          -> opciones para dropdowns (usuarios + formularios)
      DELETE /api/asignaciones/{id}/             -> elimina una asignación puntual
    """
    serializer_class = UserFormularioSerializer
    queryset = (UserFormulario.objects
                .select_related("id_usuario", "id_formulario", "id_formulario__categoria")
                .all())
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "id_usuario__nombre_usuario",
        "id_usuario__nombre",
        "id_formulario__nombre",
        "id_formulario__categoria__nombre",
    ]
    ordering_fields = ["id", "id_usuario__nombre_usuario", "id_formulario__nombre"]
    ordering = ["id"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params

        usuario = p.get("usuario")
        if usuario:
            qs = qs.filter(id_usuario__nombre_usuario__iexact=usuario)

        id_usuario = p.get("id_usuario")
        if id_usuario:
            qs = qs.filter(id_usuario__nombre_usuario__iexact=id_usuario)

        form = p.get("form") or p.get("id_formulario")
        if form:
            qs = qs.filter(id_formulario__id=form)

        categoria = p.get("categoria")
        if categoria:
            qs = qs.filter(id_formulario__categoria__id=categoria)

        categoria_nombre = p.get("categoria_nombre")
        if categoria_nombre:
            qs = qs.filter(id_formulario__categoria__nombre__icontains=categoria_nombre)

        return qs

    @extend_schema(tags=["Asignaciones"], summary="Opciones para dropdowns")
    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        """
        Devuelve listas para poblar dropdowns:
         - usuarios: top N (filtrables por ?q_user=)
         - formularios: top M (filtrables por ?q_form=, ?categoria=)
        """
        q_user = request.query_params.get("q_user", "")
        q_form = request.query_params.get("q_form", "")
        categoria = request.query_params.get("categoria")
        limit_users = int(request.query_params.get("limit_users", 20))
        limit_forms = int(request.query_params.get("limit_forms", 20))

        users_qs = Usuario.objects.all()
        if q_user:
            users_qs = users_qs.filter(
                models.Q(nombre_usuario__icontains=q_user) |
                models.Q(nombre__icontains=q_user)
            )
        users = UsuarioLiteSerializer(users_qs.order_by("nombre")[:limit_users], many=True).data

        forms_qs = Formulario.objects.select_related("categoria").all()
        if q_form:
            forms_qs = forms_qs.filter(nombre__icontains=q_form)
        if categoria:
            forms_qs = forms_qs.filter(categoria__id=categoria)
        forms = FormularioLiteSerializer(forms_qs.order_by("nombre")[:limit_forms], many=True).data

        return Response({"usuarios": users, "formularios": forms}, status=200)
    
    def get_serializer_class(self):
        if self.action == "bulk_assign":
            return AsignacionBulkSerializer   # <- usa el serializer de entrada
        return super().get_serializer_class()

    @extend_schema(
        tags=["Asignaciones"],
        summary="Asignar formularios a usuario",
        request=AsignacionBulkSerializer,     # <- define el esquema del body
        examples=[
            OpenApiExample(
                "Ejemplo básico",
                value={
                    "usuario": "linda",
                    "formularios": [
                        "3bd465c9-6d27-437f-a391-1faa17c57ded",
                        "1d234d08-7b33-4cb6-8a6e-8f0846bf8fc8"
                    ],
                    "replace": False
                },
                request_only=True,
            )
        ],
        responses={
            200: OpenApiResponse(description="Asignación realizada")
        },
    )

    @extend_schema(tags=["Asignaciones"], summary="Asignar formularios a usuario")
    @action(detail=False, methods=["post"], url_path="crear-asignacion")
    @transaction.atomic
    def bulk_assign(self, request):
        """
        Body:
        {
          "usuario": "linda" | "<uuid-usuario>",
          "formularios": ["<uuid-form-1>", "<uuid-form-2>", ...],
          "replace": false
        }
        """
        ser = AsignacionBulkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        user = ser.validated_data["user_obj"]
        form_ids = set(ser.validated_data["form_ids"])
        replace = ser.validated_data["replace"]

        actuales = set(UserFormulario.objects.filter(id_usuario=user).values_list("id_formulario", flat=True))
        nuevos = list(form_ids - actuales)
        ya_estaban = list(form_ids & actuales)

        creados = []
        for fid in nuevos:
            obj, was_created = UserFormulario.objects.get_or_create(
                id_usuario=user,
                id_formulario_id=fid,
            )
            if was_created:
                creados.append(fid)

        removidos = []
        if replace:
            a_remover = list(actuales - form_ids)
            if a_remover:
                UserFormulario.objects.filter(
                    id_usuario=user,
                    id_formulario_id__in=a_remover
                ).delete()
                removidos = a_remover

        total = UserFormulario.objects.filter(id_usuario=user).count()

        return Response({
            "ok": True,
            "usuario": {
                "id": str(user.pk),
                "nombre_usuario": user.nombre_usuario,
                "nombre": user.nombre
            },
            "asignados_nuevos": [str(x) for x in creados],
            "ya_asignados":     [str(x) for x in ya_estaban],
            "removidos":        [str(x) for x in removidos],
            "total_actual": total
        }, status=200)
    
class FormularioEntryMetaSerializer(serializers.Serializer):
    form_id = serializers.UUIDField()
    form_name = serializers.CharField()
    respuestas = serializers.IntegerField()

from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
)
from drf_spectacular.types import OpenApiTypes

class EntryExportViewSet(viewsets.GenericViewSet):
    queryset = FormularioEntry.objects.all()
    serializer_class = FormularioEntryMetaSerializer
    lookup_field = "form_id"

    # --- detalle: /api/entries/{form_id}/export/ ---
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="fmt",                                   # <-- 'fmt' en vez de 'format'
                description="Formato de exportación",
                required=False,
                type=str,
                location=OpenApiParameter.QUERY,
                enum=["xlsx", "csv", "json"],
                examples=[
                    OpenApiExample("Excel (default)", value="xlsx"),
                    OpenApiExample("CSV", value="csv"),
                    OpenApiExample("JSON", value="json"),
                ],
            ),
        ],
        responses={200: OpenApiResponse(description="Archivo", response=OpenApiTypes.BINARY)},
    )
    @action(detail=True, methods=["get"], url_path="export")
    def export_one(self, request, form_id=None):
        fmt = (request.query_params.get("fmt") or "xlsx").lower()   # <--- antes era 'format'
        fname, content, mime = content_bytes_para_un_form(form_id, fmt)
        if not content:
            return Response({"detail": "Sin respuestas para este formulario."}, status=404)
        resp = HttpResponse(content, content_type=mime)
        resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp

    # --- listado meta: /api/entries/ ---
    @extend_schema(
        operation_id="entries_list_meta",
        summary="Listar formularios (meta)",
        description="Devuelve form_id, form_name y número de respuestas.",
    )
    def list(self, request, *args, **kwargs):
        from django.db import models
        data = (FormularioEntry.objects
                .values("form_id", "form_name")
                .annotate(respuestas=models.Count("id"))
                .order_by("form_name"))
        ser = self.get_serializer(data, many=True)
        return Response(ser.data)

    # --- masivo: /api/entries/export-all/ ---
    @extend_schema(
        operation_id="entries_export_all",
        summary="Exportar todos los formularios (ZIP)",
        description="ZIP con un archivo por formulario en el formato elegido.",
        parameters=[
            OpenApiParameter(
                name="format",
                description="Formato de exportación dentro del ZIP",
                required=False,
                type=str,
                location=OpenApiParameter.QUERY,
                enum=["xlsx", "csv", "json"],
                examples=[
                    OpenApiExample("Excel (default)", value="xlsx"),
                    OpenApiExample("CSV", value="csv"),
                    OpenApiExample("JSON", value="json"),
                ],
            ),
        ],
        responses={200: OpenApiResponse(description="Archivo ZIP", response=OpenApiTypes.BINARY)},
    )
    @action(detail=False, methods=["get"], url_path="export-all")
    def export_all(self, request):
        fmt = (request.query_params.get("fmt") or "xlsx").lower()   # <--- aquí también
        fname, content = zip_bytes_todos_los_forms(fmt)
        if not content:
            return Response({"detail": "No hay respuestas para exportar."}, status=404)
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp