from django.shortcuts import render, get_object_or_404

from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Formulario, Campo, Grupo
from .serializers import FormularioSerializer, CampoSerializer, FormularioDetalleSerializer
from rest_framework.generics import RetrieveAPIView

from django.http import HttpResponse

def home(request):
    return HttpResponse("<h1>Bienvenido a la API de Formularios</h1><p>Usa /api/ para acceder a los endpoints.</p>")

class FormularioViewSet(viewsets.ModelViewSet):
    queryset = Formulario.objects.all()
    serializer_class = FormularioSerializer

# Create your views here.
class CampoViewSet(viewsets.ModelViewSet):
    queryset = Campo.objects.all()
    serializer_class = CampoSerializer

    def create(self, request, *args, **kwargs):
        formulario_id = self.kwargs.get('formulario_id', None)

        if not formulario_id:
            # Si no viene formulario_id en URL, error
            return Response({"error": "Falta formulario_id en URL"}, status=status.HTTP_400_BAD_REQUEST)

        formulario = get_object_or_404(Formulario, pk=formulario_id)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Pasar el objeto formulario al método save() del serializer
        result = serializer.save(formulario=formulario)

        # Si es Grupo, devolver mensaje personalizado
        if isinstance(result, Grupo):
            return Response({
                "mensaje": "Grupo creado correctamente",
                "grupo_id": result.id,
                "nombre": result.nombre
            }, status=status.HTTP_201_CREATED)

        # Para campos normales
        output_serializer = self.get_serializer(result)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

class FormularioDetalleAPIView(RetrieveAPIView):
    queryset = Formulario.objects.all()
    serializer_class = FormularioDetalleSerializer
    lookup_field = 'id'