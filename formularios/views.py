from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from django.db import transaction
from rest_framework.response import Response
from django.db import models
from .models import (
    Formulario,
    FormularioIndexVersion,
    Pagina,
    PaginaIndex,
    Categoria
)

from .serializers import FormularioSerializer, CategoriaSerializer, PaginaSerializer
from django.http import HttpResponse
from .services import delete_formulario_hard, duplicar_formulario

def home(request):
    return HttpResponse("<h1>Bienvenido a la API de Formularios</h1><p>Usa /api/ para acceder a los endpoints.</p>")

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer

class PaginaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Pagina.objects.all()
    serializer_class = PaginaSerializer


class FormularioViewSet(viewsets.ModelViewSet):
    queryset = Formulario.objects.all()
    serializer_class = FormularioSerializer

    @action(detail=True, methods=["post"], url_path="duplicar")
    @transaction.atomic
    def duplicar(self, request, pk=None):
        result = duplicar_formulario(pk)
        if not result.get("ok"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        nuevo = Formulario.objects.get(pk=result["formulario_nuevo_id"])
        data = FormularioSerializer(nuevo).data
        data["detalle_duplicado"] = {
            "version_nueva_id": result["version_nueva_id"],
            "paginas_copiadas": result["paginas_copiadas"]
        }
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='agregar-pagina')
    @transaction.atomic
    def agregar_pagina(self, request, pk=None):
        formulario = self.get_object()
        data = request.data

        # Decide si versionar (default = sí)
        bump = request.query_params.get("bump", "1") != "0"

        # Buscar última versión por FK correcto
        ultima_version = (FormularioIndexVersion.objects
                          .filter(formulario=formulario)
                          .order_by('-fecha_creacion')
                          .first())

        # Si no hay versión previa, crea una inicial vacía
        if ultima_version is None:
            ultima_version = FormularioIndexVersion.objects.create(formulario=formulario)

        # Si versionamos, crear nueva versión y (opcional) clonar páginas existentes
        version_destino = ultima_version
        if bump:
            version_destino = FormularioIndexVersion.objects.create(formulario=formulario)
            # Clonar páginas de la última
            for p in Pagina.objects.filter(index_version=ultima_version).order_by("secuencia"):
                copia = Pagina.objects.create(
                    index_version=version_destino,
                    formulario=formulario,
                    secuencia=p.secuencia,
                    nombre=p.nombre,
                    descripcion=p.descripcion,
                )
                PaginaIndex.objects.create(
                    id_index_version=version_destino,
                    id_pagina=copia,
                    id_formulario=formulario
                )

        # Calcular secuencia por defecto si no se envía
        if "secuencia" in data:
            secuencia = int(data.get("secuencia") or 1)
        else:
            last_seq = (Pagina.objects
                        .filter(index_version=version_destino)
                        .aggregate(max_seq=models.Max("secuencia"))
                        .get("max_seq") or 0)
            secuencia = last_seq + 1

        # Crear la nueva página en la versión destino
        nueva_pagina = Pagina.objects.create(
            index_version=version_destino,
            formulario=formulario,
            secuencia=secuencia,
            nombre=data.get('nombre', 'Nueva página'),
            descripcion=data.get('descripcion', ''),
        )
        PaginaIndex.objects.create(
            id_index_version=version_destino,
            id_pagina=nueva_pagina,
            id_formulario=formulario
        )


        return Response({
            "detail": "Página creada",
            "version": str(version_destino.id_index_version),
            "version_bumpeada": bump,
            "pagina": PaginaSerializer(nueva_pagina).data
        }, status=status.HTTP_201_CREATED)
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        formulario_id = kwargs.get("pk")
        result = delete_formulario_hard(formulario_id)
        if not result.get("ok"):
            return Response(result, status=status.HTTP_404_NOT_FOUND)
        # Estándar: 204 No Content en DELETE.
        return Response(status=status.HTTP_204_NO_CONTENT)


# class FormularioViewSet(viewsets.ModelViewSet):
#     queryset = Formulario.objects.all()
#     serializer_class = FormularioSerializer

#     def destroy(self, request, *args, **kwargs):
#         formulario_id = kwargs.get("pk")
#         result = delete_formulario_hard(formulario_id)
#         if not result.get("ok"):
#             return Response(result, status=status.HTTP_404_NOT_FOUND)
#         # estándar: 204 No Content en DELETE
#         return Response(status=status.HTTP_204_NO_CONTENT)

# class FormularioViewSet(viewsets.ModelViewSet):
#     queryset = Formulario.objects.all()
#     serializer_class = FormularioSerializer

#     def create(self, request, *args, **kwargs):
#         response = super().create(request, *args, **kwargs)

#         if request.accepted_renderer.format == 'html':
#             # Redirige con un parámetro aleatorio para forzar formulario limpio
#             return redirect(f'{request.path}?new={get_random_string(6)}')

#         return response

# # Create your views here.
# class CampoViewSet(viewsets.ModelViewSet):
#     queryset = Campo.objects.all()
#     serializer_class = CampoSerializer

#     def create(self, request, *args, **kwargs):
#         formulario_id = self.kwargs.get('formulario_id', None)

#         if not formulario_id:
#             # Si no viene formulario_id en URL, error
#             return Response({"error": "Falta formulario_id en URL"}, status=status.HTTP_400_BAD_REQUEST)

#         formulario = get_object_or_404(Formulario, pk=formulario_id)

#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)

#         # Pasar el objeto formulario al método save() del serializer
#         result = serializer.save(formulario=formulario)

#         # Si es Grupo, devolver mensaje personalizado
#         if isinstance(result, Grupo):
#             return Response({
#                 "mensaje": "Grupo creado correctamente",
#                 "grupo_id": result.id,
#                 "nombre": result.nombre
#             }, status=status.HTTP_201_CREATED)

#         # Para campos normales
#         output_serializer = self.get_serializer(result)
#         return Response(output_serializer.data, status=status.HTTP_201_CREATED)

# class FormularioDetalleAPIView(RetrieveAPIView):
#     queryset = Formulario.objects.all()
#     serializer_class = FormularioDetalleSerializer
#     lookup_field = 'id'