from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FormularioViewSet, CategoriaViewSet, PaginaViewSet, CampoViewSet, CatalogosViewSet, RolViewSet, UsuarioViewSet

router = DefaultRouter()
router.register(r'formularios', FormularioViewSet, basename='formulario')
router.register(r'categorias', CategoriaViewSet, basename='categoria')
router.register(r'paginas', PaginaViewSet, basename='pagina')  # solo lectura/depuración
router.register(r"campos",  CampoViewSet,  basename="campos")
router.register(r"catalogos", CatalogosViewSet, basename="catalogos")
router.register(r'roles', RolViewSet, basename='rol')
router.register(r'usuarios', UsuarioViewSet, basename='usuario')


urlpatterns = [
    path('', include(router.urls)),
]


urlpatterns = router.urls