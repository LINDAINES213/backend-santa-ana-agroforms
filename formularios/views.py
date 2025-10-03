from .services import _uuid32, _uuid32_no_dashes, activar_version, crear_campo_en_pagina, crear_campo_y_versionar_pagina, duplicar_formulario, uuid32
from rest_framework import status, filters, viewsets
from rest_framework.decorators import action
from django.db import transaction
from rest_framework.response import Response
from django.db import models, connection
from .models import Campo, Categoria, Formulario, Formulario_Index_Version, FormularioIndexVersion, Pagina, Pagina_Index_Version, PaginaCampo, PaginaVersion, Usuario
from django.shortcuts import get_object_or_404
from .serializers import CampoSerializer, CategoriaSerializer, CrearCampoEnPaginaSerializer, FormularioListSerializer, FormularioSerializer, PaginaConCamposSerializer, PaginaSerializer, UsuarioCreateSerializer, UsuarioDetalleSerializer
from django.http import HttpResponse
from django.utils import timezone
import uuid

from .azure_storage import AzureBlobStorageService
from .models import FuenteDatos
from .serializers import FuenteDatosSerializer, FuenteDatosCreateSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from . import services



class FuenteDatosViewSet(viewsets.ModelViewSet):
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
    def create(self, request, *args, **kwargs):
        """Subir archivo a Azure y crear registro"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        archivo = serializer.validated_data['archivo']
        nombre = serializer.validated_data['nombre']
        descripcion = serializer.validated_data.get('descripcion', '')
        
        try:
            # 1. Parse archivo para obtener preview y columnas
            file_extension = archivo.name.split('.')[-1]
            azure_service = AzureBlobStorageService()
            
            columnas, preview_data = azure_service.parse_file_preview(
                archivo, file_extension
            )
            
            # 2. Subir a Azure Blob Storage
            blob_name, blob_url = azure_service.upload_file(
                archivo, archivo.name
            )
            
            # 3. Crear registro en BD
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
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Eliminar fuente de datos y archivo de Azure"""
        fuente_datos = self.get_object()
        
        try:
            # Eliminar de Azure
            azure_service = AzureBlobStorageService()
            azure_service.delete_file(fuente_datos.blob_name)
            
            # Eliminar registro
            fuente_datos.delete()
            
            return Response(
                {"detail": "Fuente de datos eliminada exitosamente"},
                status=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            return Response(
                {"detail": f"Error eliminando archivo: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
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

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    
class PaginaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/paginas/                       -> lista páginas
    /api/paginas/{id_pagina}/           -> detalle (agrega ?include_campos=1 para devolver campos)
    /api/paginas/{id_pagina}/campos/    -> GET: solo los campos
    /api/paginas/{id_pagina}/agregar-campo/ -> POST: crear campo en esa página
    """
    queryset = Pagina.objects.all().order_by("secuencia")
    serializer_class = PaginaSerializer
    lookup_field = "id_pagina"

    def retrieve(self, request, *args, **kwargs):
        if request.query_params.get("include_campos") in ("1", "true", "True"):
            self.serializer_class = PaginaConCamposSerializer
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="campos")
    def campos(self, request, id_pagina=None):
        pagina = self.get_object()
        data = PaginaConCamposSerializer(pagina, context=self.get_serializer_context()).data
        return Response(data.get("campos", []), status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="campos")
    def agregar_campo(self, request, id_pagina=None):
        id32 = _uuid32_no_dashes(str(id_pagina))
        ser = CrearCampoEnPaginaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        out = crear_campo_en_pagina(id32, ser.validated_data)
        return Response(out, status=status.HTTP_201_CREATED)
    
class FormularioListViewSet(viewsets.ModelViewSet):
    lookup_field = "id"

    def get_queryset(self):
        # Trae solo columnas necesarias para el listado; el detail usará el serializer completo
        qs = (
            Formulario.objects
            .select_related("categoria")
            .only(
                "id",
                "categoria_id",
                "nombre",
                "descripcion",
                "permitir_fotos",
                "permitir_gps",
                "disponible_desde_fecha",
                "disponible_hasta_fecha",
                "estado",
                "forma_envio",
                "es_publico",
                "auto_envio",
            )
        )
        return qs

    def get_serializer_class(self):
        # Usa el serializer liviano en list; el completo en retrieve/otros
        if self.action == "list":
            return FormularioListSerializer
        return FormularioSerializer

class FormularioViewSet(viewsets.ModelViewSet):
    queryset = Formulario.objects.all()
    serializer_class = FormularioSerializer
    lookup_field = "id"

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, *args, **kwargs):
        formulario = self.get_object()
        nuevo_nombre = request.data.get("nombre")  # opcional
        clon = services.duplicar_formulario(formulario, nuevo_nombre=nuevo_nombre)
        data = FormularioSerializer(clon, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)
        
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """
        DELETE /api/formularios/{id}/
        Deletes a complete form with all its related data
        """
        try:
            formulario = self.get_object()
            formulario_id = str(formulario.id)
            
            # Since models are unmanaged, we need to manually handle cascading deletes
            self._delete_formulario_cascade(formulario_id)
            
            return Response({
                "detail": f"Formulario {formulario_id} eliminado exitosamente",
                "deleted_id": formulario_id
            }, status=status.HTTP_204_NO_CONTENT)
            
        except Formulario.DoesNotExist:
            return Response(
                {"detail": "Formulario no encontrado."}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": f"Error eliminando formulario: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    
    def _delete_formulario_cascade(self, formulario_id: str):
            """
            Elimina un formulario y TODA su jerarquía usando ORM (orden seguro).
            Compatible con PostgreSQL y evita SQL específico de SQL Server.
            """
            with transaction.atomic():
                # 0) Traer el formulario (UUID real, no en 32 chars)
                form = Formulario.objects.get(pk=formulario_id)

                # 1) Todas las páginas del formulario (UUID)
                pages = list(Pagina.objects.filter(formulario_id=form).only("id_pagina"))
                page_ids = [p.id_pagina for p in pages]
                page_ids_32 = [uuid.UUID(str(pid)).hex for pid in page_ids]  # para comparar con PaginaVersion.id_pagina (char(32))

                # 2) Todas las versiones de esas páginas (char(32))
                pv_qs = PaginaVersion.objects.filter(id_pagina__in=page_ids_32)
                pv_ids = list(pv_qs.values_list("id_pagina_version", flat=True))

                # 3) Enlaces PaginaCampo -> BORRAR PRIMERO (depende de PaginaVersion y Campo)
                if pv_ids:
                    PaginaCampo.objects.filter(id_pagina_version_id__in=pv_ids).delete()

                # (Opcional) Borrar Campos huérfanos que ya no estén enlazados a ninguna página
                Campo.objects.filter(enlaces_pagina__isnull=True).delete()

                # 4) Si tienes la tabla de punteros de páginas a index version (PaginaIndexVersion),
                #    bórrala por ORM (está definida en tus modelos como Formulario -> PaginaIndexVersion).
                try:
                    from .models import PaginaIndexVersion
                    if pages:
                        PaginaIndexVersion.objects.filter(id_pagina__in=pages).delete()
                except Exception:
                    # Si no existe el modelo/tabla en tu instalación, ignorar
                    pass

                # 5) Borrar el historial de versiones por página
                pv_qs.delete()

                # 6) Borrar las páginas del formulario
                if page_ids:
                    Pagina.objects.filter(id_pagina__in=page_ids).delete()

                # 7) Borrar la tabla histórica de vínculo formulario-index (formularios_formularios_index_version)
                #    Está modelada como Formulario_Index_Version con O2O a FormularioIndexVersion
                fiv_qs = FormularioIndexVersion.objects.filter(formulario_id=form)
                if fiv_qs.exists():
                    Formulario_Index_Version.objects.filter(id_index_version__in=fiv_qs).delete()

                # 8) Borrar versiones de formulario
                fiv_qs.delete()

                # 10) Finalmente, borrar el formulario
                form.delete()


    @action(detail=True, methods=['post'], url_path='agregar-pagina')
    @transaction.atomic
    def agregar_pagina(self, request, *args, **kwargs):
        formulario = self.get_object()
        bump = request.query_params.get("bump", "1") != "0"

        # última versión o crea v1
        ultima_version = (
            FormularioIndexVersion.objects
            .filter(formulario_id=formulario).order_by('-fecha_creacion').first()
        ) or FormularioIndexVersion.objects.create(formulario_id=formulario)

        version_destino = ultima_version
        if bump:
            version_destino = FormularioIndexVersion.objects.create(formulario_id=formulario)
            # mover puntero de todas las páginas existentes a la nueva versión
            for p in Pagina.objects.filter(formulario_id=formulario).only("id_pagina"):
                Pagina_Index_Version.objects.update_or_create(
                    id_pagina=p,
                    defaults={"id_index_version": version_destino},
                )

        # calcular secuencia
        last_seq = (
            Pagina.objects.filter(formulario_id=formulario)
            .aggregate(max_seq=models.Max("secuencia"))
            .get("max_seq") or 0
        )
        secuencia = last_seq + 1

        # crear NUEVA página lógica (id_pagina nuevo SOLO porque es una página nueva)
        nueva_pagina = Pagina.objects.create(
            index_version=version_destino,     # versión de nacimiento
            formulario_id=formulario,
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
            id_pagina=_uuid32_no_dashes(str(nueva_pagina.id_pagina)),
            fecha_creacion=timezone.now(),
        )

        return Response({"ok": True, "id_pagina": str(nueva_pagina.id_pagina)}, status=201)

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by("nombre")
    lookup_field = "nombre_usuario"   # clave
    serializer_class = UsuarioDetalleSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCreateSerializer
        return UsuarioDetalleSerializer

    # @action(detail=True, methods=["put"], url_path="roles")
    # def replace_roles(self, request, nombre_usuario=None):
    #     user = self.get_object()
    #     ser = UsuarioReplaceRolesSerializer(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     ser.update(user, ser.validated_data)
    #     return Response(UsuarioDetalleSerializer(user, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)


class CampoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/campos/          -> todos los campos (paginado)
    GET /api/campos/{id}/     -> detalle de un campo
    Filtros:
      ?search=texto           (busca en nombre_campo, etiqueta, clase, tipo)
      ?ordering=nombre_campo  (o -nombre_campo, tipo, clase, etiqueta)
    """
    queryset = Campo.objects.all().order_by("nombre_campo")
    serializer_class = CampoSerializer
    lookup_field = "id_campo"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre_campo", "etiqueta", "clase", "tipo"]
    ordering_fields = ["nombre_campo", "tipo", "clase", "etiqueta"]