from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Formulario, Campo, Grupo

class FormularioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Formulario
        fields = ['id', 'nombre', 'descripcion', 'fecha_creacion']
        read_only_fields = ['fecha_creacion']

class CampoSerializer(serializers.ModelSerializer):
    # Este flag que llega desde el frontend
    es_grupo = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model  = Campo
        fields = [
            'id', 'formulario', 'grupo', 'nombre_campo',
            'tipo', 'requerido', 'pertenece_grupo', 'es_grupo',
        ]
        read_only_fields = ['formulario']        # lo inyectaremos en la vista

    def create(self, validated_data):
        es_grupo = validated_data.pop('es_grupo', False)
        formulario = validated_data['formulario']
        nombre_campo = validated_data['nombre_campo']

        if es_grupo:
            # Si es grupo, crear objeto Grupo
            grupo = Grupo.objects.create(formulario=formulario, nombre=nombre_campo)
            return grupo  

        return Campo.objects.create(**validated_data)

class CampoSoloLecturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campo
        fields = ['id', 'nombre_campo', 'tipo', 'requerido', 'pertenece_grupo', 'grupo']


class GrupoConCamposSerializer(serializers.ModelSerializer):
    campos = CampoSoloLecturaSerializer(many=True, read_only=True)

    class Meta:
        model = Grupo
        fields = ['id', 'nombre', 'campos']


class FormularioDetalleSerializer(serializers.ModelSerializer):
    campos = serializers.SerializerMethodField()
    grupos = GrupoConCamposSerializer(many=True, read_only=True)

    class Meta:
        model = Formulario
        fields = ['id', 'nombre', 'descripcion', 'fecha_creacion', 'campos', 'grupos']

    def get_campos(self, obj):
        # Solo campos que NO pertenecen a ningún grupo
        campos = obj.campos.filter(grupo__isnull=True)
        return CampoSoloLecturaSerializer(campos, many=True).data