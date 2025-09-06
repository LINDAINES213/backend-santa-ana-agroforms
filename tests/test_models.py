from formularios.models import Categoria

def test_category_str():
    c = Categoria.objects.create(nombre='Cat A')
    assert str(c) == 'Cat A'
