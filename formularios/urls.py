from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FormularioViewSet, CategoriaViewSet

router = DefaultRouter()
router.register(r'formularios', FormularioViewSet, basename='formulario')
router.register(r'categorias', CategoriaViewSet, basename='categoria')


urlpatterns = [
    path('', include(router.urls)),
]


urlpatterns = router.urls