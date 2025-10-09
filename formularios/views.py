from .services import _uuid32, _uuid32_no_dashes, activar_version, crear_campo_en_pagina, crear_campo_y_versionar_pagina, duplicar_formulario, uuid32
from rest_framework import status, filters, viewsets
from rest_framework.decorators import action
from django.db import transaction
from rest_framework.response import Response
from django.db import models, connection
from .models import Campo, CampoGrupo, Categoria, Formulario, Formulario_Index_Version, FormularioIndexVersion, Grupo, Pagina, Pagina_Index_Version, PaginaCampo, PaginaVersion, UserFormulario, Usuario
from django.shortcuts import get_object_or_404
from .serializers import AsignacionBulkSerializer, CampoSerializer, CampoUpdateSerializer, CategoriaSerializer, CrearCampoEnPaginaSerializer, FormularioListSerializer, FormularioLiteSerializer, FormularioSerializer, FormularioUpdateSerializer, PaginaConCamposSerializer, PaginaSerializer, PaginaUpdateSerializer, UserFormularioSerializer, UsuarioCreateSerializer, UsuarioDetalleSerializer, GrupoSerializer, UsuarioLiteSerializer, UsuarioUpdateSerializer
from django.http import HttpResponse
from django.utils import timezone
import uuid
from django.db.models import Q
from rest_framework import mixins



from .azure_storage import AzureBlobStorageService
from .models import FuenteDatos
from .serializers import FuenteDatosSerializer, FuenteDatosCreateSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from . import services
from rest_framework import serializers as drf_serializers
from django.db.models.deletion import ProtectedError




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
    queryset = Categoria.objects.all().order_by("nombre")
    serializer_class = CategoriaSerializer
    lookup_field = "id"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # Bloquear explícitamente si hay formularios que usan esta categoría
        if Formulario.objects.filter(categoria=instance).exists():
            return Response(
                {"detail": "No se puede eliminar: hay formularios que usan esta categoría."},
                status=status.HTTP_409_CONFLICT
            )
        return super().destroy(request, *args, **kwargs)
    
class PaginaViewSet(viewsets.ModelViewSet):
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

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return PaginaUpdateSerializer
        return PaginaSerializer

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

        # 2) Si te mandaron un grupo, enlaza automáticamente el campo al grupo
        gid = request.data.get("grupo") or request.data.get("id_grupo")

        # fallback: si venía dentro de config (id_group)
        if not gid:
            cfg = ser.validated_data.get("config") or {}
            if isinstance(cfg, str):
                import json
                try:
                    cfg = json.loads(cfg)
                except Exception:
                    cfg = {}
            v = cfg.get("id_group")
            if isinstance(v, (list, tuple)) and v:
                gid = v[0]
            elif isinstance(v, str):
                gid = v

        if gid:
            try:
                g = Grupo.objects.get(pk=str(gid))
            except Grupo.DoesNotExist:
                return Response(
                    {"detail": f"El grupo '{gid}' no existe. Crea primero el campo de clase 'group' que lo define."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ‘out’ puede traer "id_campo" (versión A) o "campo_id" (versión B) según tu services.py
            campo_id = out.get("id_campo") or out.get("campo_id")
            if not campo_id:
                return Response({"detail": "No se pudo resolver id_campo creado."}, status=500)

            CampoGrupo.objects.get_or_create(
                id_grupo=g,
                id_campo_id=str(campo_id)  # Campo.id_campo es char(32) en tu modelo
            )

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

    def get_serializer_class(self):
        if self.action == "list":
            return FormularioSerializer
        if self.action in ("partial_update", "update"):
            return FormularioUpdateSerializer
        return FormularioSerializer  # create / retrieve

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
    # serializer_class = UsuarioDetalleSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCreateSerializer
        if self.action in ("partial_update", "update"):
            return UsuarioUpdateSerializer
        return UsuarioDetalleSerializer

    # @action(detail=True, methods=["put"], url_path="roles")
    # def replace_roles(self, request, nombre_usuario=None):
    #     user = self.get_object()
    #     ser = UsuarioReplaceRolesSerializer(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     ser.update(user, ser.validated_data)
    #     return Response(UsuarioDetalleSerializer(user, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)


class CampoViewSet(viewsets.ModelViewSet):
    """
    GET /api/campos/          -> todos los campos (paginado)
    GET /api/campos/{id}/     -> detalle de un campo
    Filtros:
      ?search=texto           (busca en nombre_campo, etiqueta, clase, tipo)
      ?ordering=nombre_campo  (o -nombre_campo, tipo, clase, etiqueta)
    """
    queryset = Campo.objects.all().order_by("nombre_campo")
    # serializer_class = CampoSerializer
    lookup_field = "id_campo"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre_campo", "etiqueta", "clase", "tipo"]
    ordering_fields = ["nombre_campo", "tipo", "clase", "etiqueta"]

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return CampoUpdateSerializer
        return CampoSerializer

class GrupoViewSet(viewsets.ModelViewSet):
    queryset = Grupo.objects.all().order_by("nombre")
    serializer_class = type("GrupoSerializer", (drf_serializers.ModelSerializer,), {
        "Meta": type("Meta", (), {"model": Grupo, "fields": ("id_grupo","nombre","id_campo_group")})
    })

    @action(detail=True, methods=["get","post"], url_path="campos")
    def campos(self, request, pk=None):
        grupo = self.get_object()
        if request.method.lower() == "get":
            rows = (CampoGrupo.objects
                    .filter(id_grupo=grupo)
                    .select_related("id_campo")
                    .order_by("sequence","id_campo_id"))
            data = [{"id_campo": r.id_campo_id,
                     "sequence": r.sequence,
                     "etiqueta": r.id_campo.etiqueta,
                     "clase": r.id_campo.clase,
                     "tipo": r.id_campo.tipo} for r in rows]
            return Response(data, 200)

        id_campo = request.data.get("id_campo")
        seq = request.data.get("sequence")
        if seq is None:
            mx = CampoGrupo.objects.filter(id_grupo=grupo).aggregate(models.Max("sequence"))["sequence__max"] or 0
            seq = mx + 1
        obj, created = CampoGrupo.objects.get_or_create(
            id_grupo=grupo, id_campo_id=id_campo, defaults={"sequence": seq}
        )
        if not created:
            obj.sequence = seq
            obj.save(update_fields=["sequence"])
        return Response({"ok": True, "id_grupo": grupo.pk, "id_campo": id_campo, "sequence": seq}, 201)


class GrupoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Grupo.objects.all().order_by("nombre")
    serializer_class = GrupoSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        pagina = self.request.query_params.get("pagina")  # UUID con o sin guiones o char(32)

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
            # solo grupos cuyos CAMPOS group estén en la página (última versión)
            campo_group_ids = (PaginaCampo.objects
                               .filter(id_pagina_version=pv.id_pagina_version,
                                       id_campo__clase__iexact="group")
                               .values_list("id_campo", flat=True))
            qs = qs.filter(id_campo_group_id__in=list(campo_group_ids))
        return qs

    # endpoint liviano para “combos”
    @action(detail=False, methods=["get"], url_path="select")
    def select(self, request):
        qs = self.get_queryset()[:50]  # limita resultados
        return Response([{"value": g.id_grupo, "label": g.nombre} for g in qs])

class AsignacionViewSet(viewsets.ModelViewSet):
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
            # si decides seguir aceptando este parámetro, que también sea nombre_usuario:
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

        # crear nuevas asignaciones evitando duplicados
        UserFormulario.objects.bulk_create(
            [UserFormulario(id_usuario=user, id_formulario_id=fid) for fid in nuevos],
            ignore_conflicts=True
        )

        removidos = []
        if replace:
            a_remover = list(actuales - form_ids)
            if a_remover:
                UserFormulario.objects.filter(id_usuario=user, id_formulario_id__in=a_remover).delete()
                removidos = a_remover

        total = UserFormulario.objects.filter(id_usuario=user).count()

        return Response({
            "ok": True,
            "usuario": {"id": str(user.pk), "nombre_usuario": user.nombre_usuario, "nombre": user.nombre},
            "asignados_nuevos": [str(x) for x in nuevos],
            "ya_asignados":     [str(x) for x in ya_estaban],
            "removidos":        [str(x) for x in removidos],
            "total_actual": total
        }, status=200)