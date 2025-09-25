from .services import _uuid32_no_dashes, activar_version, crear_campo_en_pagina, crear_campo_y_versionar_pagina, duplicar_formulario_orm
from rest_framework import status, filters, viewsets
from rest_framework.decorators import action
from django.db import transaction
from rest_framework.response import Response
from django.db import models, connection
from .models import Campo, Categoria, Formulario, FormularioIndexVersion, Pagina, Rol, Usuario
from django.shortcuts import get_object_or_404
from .serializers import CampoSerializer, CategoriaSerializer, CrearCampoEnPaginaSerializer, FormularioSerializer, PaginaConCamposSerializer, PaginaSerializer, RolCreateUpdateSerializer, RolSerializer, UsuarioCreateSerializer, UsuarioDetalleSerializer, UsuarioReplaceRolesSerializer
from django.http import HttpResponse

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

class FormularioViewSet(viewsets.ModelViewSet):
    queryset = Formulario.objects.all()
    serializer_class = FormularioSerializer
    lookup_field = "id"

    @action(detail=True, methods=["post"], url_path="duplicar")
    def duplicar(self, request, id=None):
        try:
            out = duplicar_formulario_orm(id)
            return Response(out, status=status.HTTP_201_CREATED)
        except Formulario.DoesNotExist:
            return Response({"detail": "Formulario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": f"Fallo duplicando: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
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
        Manually handle cascading deletes for unmanaged models
        Order is important to respect foreign key constraints
        """
        with connection.cursor() as cursor:
            # Convert UUID to 32-char format for database queries
            formulario_id_32 = formulario_id.replace('-', '').lower()
            
            # 1. Delete campo-pagina relationships first (PaginaCampo)
            cursor.execute("""
                DELETE pc FROM formularios_pagina_campo pc
                INNER JOIN formularios_pagina_version pv ON pc.id_pagina_version = pv.id_pagina_version  
                INNER JOIN formularios_pagina p ON pv.id_pagina = p.id_pagina
                WHERE p.formulario_id = %s
            """, [formulario_id_32])
            
            # 2. Delete page versions (PaginaVersion)
            cursor.execute("""
                DELETE pv FROM formularios_pagina_version pv
                INNER JOIN formularios_pagina p ON pv.id_pagina = p.id_pagina
                WHERE p.formulario_id = %s
            """, [formulario_id_32])
            
            # 3. Delete page index version pointers (Pagina_Index_Version)
            cursor.execute("""
                DELETE piv FROM formularios_pagina_index_version piv
                INNER JOIN formularios_pagina p ON piv.id_pagina = p.id_pagina
                WHERE p.formulario_id = %s
            """, [formulario_id_32])
            
            # 4. Delete pages (Pagina)
            cursor.execute("""
                DELETE FROM formularios_pagina 
                WHERE formulario_id = %s
            """, [formulario_id_32])
            
            # 5. Delete form index version history (Formulario_Index_Version)
            cursor.execute("""
                DELETE fiv FROM formularios_formularios_index_version fiv
                INNER JOIN formularios_formularioindexversion fv ON fiv.id_index_version = fv.id_index_version
                WHERE fv.formulario_id = %s
            """, [formulario_id_32])
            
            # 6. Delete form versions (FormularioIndexVersion)
            cursor.execute("""
                DELETE FROM formularios_formularioindexversion 
                WHERE formulario_id = %s
            """, [formulario_id_32])
            
            # 7. Delete role-form relationships (RolFormulario)
            cursor.execute("""
                DELETE FROM formularios_rol_formulario 
                WHERE id_formulario = %s
            """, [formulario_id_32])
            
            # 8. Finally, delete the form itself (Formulario)
            cursor.execute("""
                DELETE FROM formularios_formulario 
                WHERE id = %s
            """, [formulario_id_32])

    @action(detail=True, methods=['post'], url_path='agregar-pagina')
    @transaction.atomic
    def agregar_pagina(self, request, id=None):
        formulario = self.get_object()
        data = request.data

        # ¿Creamos nueva versión? (por defecto sí: bump=1)
        bump = request.query_params.get("bump", "1") != "0"

        # Última versión existente por fecha (si no hay, creamos v1)
        ultima_version = (FormularioIndexVersion.objects
                  .filter(formulario_id=formulario)   # <-- FK correcto
                  .order_by('-fecha_creacion')
                  .first())

        if ultima_version is None:
            ultima_version = FormularioIndexVersion.objects.create(formulario_id=formulario)

        version_destino = ultima_version

        activar_version(formulario=formulario, nueva_version=version_destino)

        # Si se solicita "bump", creamos una nueva versión y clonamos SOLO páginas
        if bump:
            version_destino = FormularioIndexVersion.objects.create(formulario_id=formulario)

            # Clonar TODAS las páginas de la última versión hacia la nueva (sin campos por ahora)
            paginas_src = (Pagina.objects
                           .filter(index_version=ultima_version)
                           .order_by("secuencia"))
            for p in paginas_src:
                Pagina.objects.create(
                    index_version=version_destino,
                    formulario_id=formulario,   # <- OJO: es formulario_id
                    secuencia=p.secuencia,
                    nombre=p.nombre,
                    descripcion=p.descripcion,
                )

        # Calcular secuencia por defecto si no viene
        if "secuencia" in data and str(data.get("secuencia")).strip() not in ("", "0", "None"):
            secuencia = int(data.get("secuencia"))
        else:
            last_seq = (Pagina.objects
                        .filter(index_version=version_destino)
                        .aggregate(max_seq=models.Max("secuencia"))
                        .get("max_seq") or 0)
            secuencia = last_seq + 1

        # Crear la nueva página en la versión destino
        nueva_pagina = Pagina.objects.create(
            index_version=version_destino,
            formulario_id=formulario,        # <- OJO: es formulario_id
            secuencia=secuencia,
            nombre=data.get('nombre', 'Nueva página'),
            descripcion=data.get('descripcion', ''),
        )

        return Response({
            "detail": f"Página creada en versión {str(version_destino.id_index_version)}",
            "formulario_id": str(formulario.id),
            "version_id": str(version_destino.id_index_version),
            "pagina": {
                "id_pagina": str(nueva_pagina.id_pagina),
                "secuencia": nueva_pagina.secuencia,
                "nombre": nueva_pagina.nombre,
                "descripcion": nueva_pagina.descripcion,
            }
        }, status=status.HTTP_201_CREATED)

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by("nombre")
    lookup_field = "nombre_usuario"   # clave
    serializer_class = UsuarioDetalleSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCreateSerializer
        return UsuarioDetalleSerializer

    @action(detail=True, methods=["put"], url_path="roles")
    def replace_roles(self, request, nombre_usuario=None):
        user = self.get_object()
        ser = UsuarioReplaceRolesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.update(user, ser.validated_data)
        return Response(UsuarioDetalleSerializer(user, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)

class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all().order_by("nombre")
    serializer_class = RolSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nombre", "descripcion"]   # ?search=admin
    ordering_fields = ["nombre", "id"]          # ?ordering=nombre  | ?ordering=-nombre

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return RolCreateUpdateSerializer
        return RolSerializer

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_create(self, request):
        """
        Crea roles en lote sin duplicar por nombre (case-insensitive).
        Body: [{ "nombre": "Admin", "descripcion": "..." }, ...]
        """
        items = request.data
        if not isinstance(items, list):
            return Response({"detail": "Se esperaba una lista de objetos."},
                            status=status.HTTP_400_BAD_REQUEST)

        creados, existentes, errores = [], [], []

        for i, item in enumerate(items, start=1):
            nombre = (item or {}).get("nombre")
            descripcion = (item or {}).get("descripcion", "")
            if not nombre or not isinstance(nombre, str):
                errores.append({"index": i, "error": "nombre requerido"})
                continue

            # buscar case-insensitive
            obj = Rol.objects.filter(nombre__iexact=nombre).first()
            if obj:
                existentes.append({"index": i, "id": str(obj.id), "nombre": obj.nombre})
                continue

            # Crear usando el serializer para validar reglas (longitud, etc.)
            ser = RolCreateUpdateSerializer(data={"nombre": nombre, "descripcion": descripcion})
            if ser.is_valid():
                obj = ser.save()
                creados.append({"index": i, "id": str(obj.id), "nombre": obj.nombre})
            else:
                errores.append({"index": i, "error": ser.errors})

        return Response(
            {"creados": creados, "existentes": existentes, "errores": errores},
            status=status.HTTP_201_CREATED if creados else status.HTTP_200_OK
        )

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