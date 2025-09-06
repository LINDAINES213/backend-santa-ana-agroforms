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
    PaginaCampoActual,
    PaginaIndex,
    Categoria,
    ClaseCampo,
    Campo, 
    FormularioActualVersion, 
    PaginaActualVersion
)

from .serializers import FormularioSerializer, CategoriaSerializer, PaginaSerializer, CampoSerializer, PaginaConCamposSerializer, FormularioActualSerializer, PaginaActualSerializer
from django.http import HttpResponse
from .services import delete_formulario_hard, duplicar_formulario, activar_version, _clonar_paginas_y_campos

def home(request):
    return HttpResponse("<h1>Bienvenido a la API de Formularios</h1><p>Usa /api/ para acceder a los endpoints.</p>")

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer

class PaginaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/paginas -> páginas VIGENTES (PaginaActualVersion)
    GET /api/paginas/{id} -> intenta la VIGENTE por ese id de página; si no hay, cae a la base.
    """
    queryset = (Pagina.objects
                .select_related("formulario","index_version")
                .prefetch_related("campos"))
    serializer_class = PaginaSerializer

    def get_serializer_context(self): 
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def list(self, request, *args, **kwargs):
        """
        Lista SOLO las páginas de la versión ACTUAL de cada formulario, en orden.
        """
        qs = (PaginaActualVersion.objects
              .select_related("pagina", "formulario")
              .order_by("formulario_id"))
        ser = PaginaActualSerializer(qs, many=True, context=self.get_serializer_context())
        return Response(ser.data, status=200)

    def retrieve(self, request, *args, **kwargs):
        """
        Devuelve la página ACTUAL si existe (por id_pagina); si no, cae a la página base.
        Puedes activar include_campos=1 para la versión base también.
        """
        pk = kwargs.get(self.lookup_field or "pk")
        actual = (PaginaActualVersion.objects
                  .select_related("pagina", "formulario")
                  .filter(pagina_id=pk)
                  .first())
        if actual:
            ser = PaginaActualSerializer(actual, context=self.get_serializer_context())
            return Response(ser.data, status=200)

        # Fallback a la entidad base (no vigente)
        self.serializer_class = (PaginaConCamposSerializer
                                 if request.query_params.get("include_campos") in ("1","true","True")
                                 else PaginaSerializer)
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=["post"], url_path="campos-actual")
    @transaction.atomic
    def crear_campo_actual(self, request, pk=None):
        """
        Crea un Campo sobre la PÁGINA VIGENTE (PaginaActualVersion).
        1) Crea el Campo en la tabla madre 'Campo' (FK a Pagina).
        2) Crea su proyección en 'PaginaCampoActual' para que aparezca en el GET vigente.
        """
        # 1) Página vigente
        actual = (PaginaActualVersion.objects
                  .select_related("pagina", "formulario", "version_activa")
                  .filter(pagina_id=pk)
                  .first())
        if not actual:
            return Response(
                {"detail": "Esta página no tiene versión ACTUAL publicada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pagina = actual.pagina

        # 2) Serializador del Campo 
        payload = request.data.copy()
        payload["pagina"] = str(pagina.id_pagina) 
        ser = CampoSerializer(data=payload, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)

        # 3) Secuencia por defecto si no viene
        if "sequence" in payload and payload["sequence"] not in (None, "", 0):
            ser.validated_data["sequence"] = int(payload["sequence"])
        else:
            last = pagina.campos.aggregate(mx=models.Max("sequence")).get("mx") or 0
            ser.validated_data["sequence"] = last + 1

        # 4) Crear Campo en la madre
        campo = ser.save(pagina=pagina)

        # 5) Espejo en 'PaginaCampoActual'
        PaginaCampoActual.objects.create(
            pagina_actual=actual,
            campo=campo,
            orden=campo.sequence,
            requerido=campo.requerido,
            config=campo.config,
        )

        # 6) Respuesta: el campo recién creado
        return Response(CampoSerializer(campo).data, status=status.HTTP_201_CREATED)

# class PaginaViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = (Pagina.objects
#                 .select_related("formulario","index_version")
#                 .prefetch_related("campos"))
#     serializer_class = PaginaSerializer

#     def get_serializer_context(self): 
#         ctx = super().get_serializer_context()
#         ctx["request"] = self.request
#         return ctx

#     @action(detail=True, methods=["get","post"], url_path="campos")
#     @transaction.atomic
#     def campos(self, request, pk=None):
#         pagina = self.get_object()

#         if request.method == "GET":
#             qs = pagina.campos.all().order_by("sequence","id_campo")
#             return Response(CampoSerializer(qs, many=True).data, status=200)

#         # POST: crear
#         payload = request.data.copy()
#         payload["pagina"] = str(pagina.id_pagina)
#         ser = CampoSerializer(data=payload)
#         ser.is_valid(raise_exception=True)

#         if not payload.get("sequence"):
#             last = pagina.campos.aggregate(mx=models.Max("sequence")).get("mx") or 0
#             ser.validated_data["sequence"] = last + 1

#         obj = ser.save(pagina=pagina)
#         return Response(CampoSerializer(obj).data, status=201)
    
#     def retrieve(self, request, *args, **kwargs):
#         self.serializer_class = (PaginaConCamposSerializer
#                                  if request.query_params.get("include_campos") in ("1","true","True")
#                                  else PaginaSerializer)
#         return super().retrieve(request, *args, **kwargs)

class CampoViewSet(viewsets.ModelViewSet):
    queryset = Campo.objects.all().select_related("pagina")
    serializer_class = CampoSerializer

    @action(detail=False, methods=["post"], url_path="reordenar")
    @transaction.atomic
    def reordenar(self, request):
        """
        Body: { "items": [ {"id_campo":"...", "sequence":1}, ... ] }
        """
        items = request.data.get("items") or []
        mapa = { str(i["id_campo"]): int(i["sequence"]) for i in items if "id_campo" in i and "sequence" in i }
        objs = Campo.objects.filter(id_campo__in=list(mapa.keys()))
        for c in objs:
            c.sequence = mapa[str(c.id_campo)]
        Campo.objects.bulk_update(objs, ["sequence"])
        return Response({"updated": len(objs)}, status=200)

class CatalogosViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["get"], url_path="clases-campo")
    def clases(self, request):
        data = [{"clase": c.clase, "schema": c.schema}
                for c in ClaseCampo.objects.all().order_by("clase")]
        return Response(data, status=200)

    @action(detail=False, methods=["get"], url_path="check-clase")
    def check_clase(self, request):
        clase = (request.query_params.get("clase") or "").strip().lower()
        raw = [ (c.clase or "") for c in ClaseCampo.objects.all() ]
        norm = [ s.strip().lower() for s in raw ]
        return Response({
            "input_raw": request.query_params.get("clase", ""),
            "input_norm": clase,
            "catalog_raw": raw,
            "catalog_norm": norm,
            "match": clase in norm
        }, status=200)


class FormularioViewSet(viewsets.ModelViewSet):
    queryset = (Formulario.objects
                .select_related("categoria")
                .prefetch_related("paginas__index_version", "paginas__campos"))
    serializer_class = FormularioSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx
    
    def list(self, request, *args, **kwargs):
        qs = (FormularioActualVersion.objects
              .select_related("formulario", "index_version"))
        ser = FormularioActualSerializer(qs, many=True, context=self.get_serializer_context())
        return Response(ser.data, status=200)

    def retrieve(self, request, *args, **kwargs):
        formulario_id = kwargs.get(self.lookup_field or "pk")
        obj = (FormularioActualVersion.objects
               .select_related("formulario", "index_version")
               .get(formulario_id=formulario_id))
        ser = FormularioActualSerializer(obj, context=self.get_serializer_context())
        return Response(ser.data, status=200)

    @action(detail=True, methods=["post"], url_path="duplicar")
    @transaction.atomic
    def duplicar(self, request, pk=None):
        result = duplicar_formulario(pk)
        if not result.get("ok"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        nuevo = Formulario.objects.get(pk=result["formulario_nuevo_id"])
        data = FormularioSerializer(nuevo, context=self.get_serializer_context()).data
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

        bump = request.query_params.get("bump", "1") != "0"

        ultima_version = (FormularioIndexVersion.objects
                          .filter(formulario=formulario)
                          .order_by('-fecha_creacion')
                          .first())

        if ultima_version is None:
            ultima_version = FormularioIndexVersion.objects.create(formulario=formulario)

        version_destino = ultima_version
        if bump:
            version_destino = FormularioIndexVersion.objects.create(formulario=formulario)
            _clonar_paginas_y_campos(ultima_version, version_destino, formulario)
            # for p in Pagina.objects.filter(index_version=ultima_version).order_by("secuencia"):
            #     copia = Pagina.objects.create(
            #         index_version=version_destino,
            #         formulario=formulario,
            #         secuencia=p.secuencia,
            #         nombre=p.nombre,
            #         descripcion=p.descripcion,
            #     )
            #     PaginaIndex.objects.create(
            #         id_index_version=version_destino,
            #         id_pagina=copia,
            #         id_formulario=formulario
            #     )


        # Calcular secuencia por defecto si no se envía
        if "secuencia" in data and str(data.get("secuencia")).strip() not in ("", "0", "None"):
            secuencia = int(data.get("secuencia"))
        else:
            last_seq = (Pagina.objects
                        .filter(index_version=version_destino)
                        .aggregate(max_seq=models.Max("secuencia"))
                        .get("max_seq") or 0)
            secuencia = last_seq + 1

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

        # ✅ AHORA sí, activar para materializar PaginaActualVersion con la nueva página
        activar_version(formulario, version_destino)


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