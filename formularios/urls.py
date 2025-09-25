from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoriaViewSet, FormularioViewSet, PaginaViewSet, UsuarioViewSet, RolViewSet, CampoViewSet, FormularioListViewSet

router = DefaultRouter()
router.register(r'formularios', FormularioViewSet, basename='formulario')
router.register(r'categorias', CategoriaViewSet, basename='categoria')
router.register(r'paginas', PaginaViewSet, basename='pagina')
router.register(r'usuarios', UsuarioViewSet, basename='usuario')
router.register(r'roles', RolViewSet, basename='rol')
router.register(r"campos",  CampoViewSet,  basename="campos")
router.register(r"formularios-lite", FormularioListViewSet, basename="formularios-lite")


urlpatterns = [
    path('', include(router.urls)),
]


urlpatterns = router.urls