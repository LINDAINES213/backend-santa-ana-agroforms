from django.shortcuts import render, get_object_or_404

from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Formulario, Campo, Grupo
from .serializers import FormularioSerializer, CampoSerializer, FormularioDetalleSerializer
from rest_framework.generics import RetrieveAPIView

class FormularioViewSet(viewsets.ModelViewSet):
    queryset = Formulario.objects.all()
    serializer_class = FormularioSerializer

# Create your views here.
class CampoViewSet(viewsets.ModelViewSet):
    queryset = Campo.objects.all()
    serializer_class = CampoSerializer

    def create(self, request, *args, **kwargs):
        formulario_id = self.kwargs.get('formulario_id')
        formulario = get_object_or_404(Formulario, pk=formulario_id)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        
        validated_data = serializer.validated_data
        validated_data['formulario'] = formulario

        result = serializer.create(validated_data)

        # Si es grupo
        if isinstance(result, Grupo):
            return Response({
                "mensaje": "Grupo creado correctamente",
                "grupo_id": result.id,
                "nombre": result.nombre
            }, status=status.HTTP_201_CREATED)

        # Si es campo, usar serializer normalmente
        output_serializer = self.get_serializer(result)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

class FormularioDetalleAPIView(RetrieveAPIView):
    queryset = Formulario.objects.all()
    serializer_class = FormularioDetalleSerializer
    lookup_field = 'id'