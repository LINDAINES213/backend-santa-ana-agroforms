from formularios.serializers import CategoriaSerializer

def test_category_serializer_validates_required_fields():
    s = CategoriaSerializer(data={})  # falta 'nombre'
    assert not s.is_valid()
    assert 'nombre' in s.errors
