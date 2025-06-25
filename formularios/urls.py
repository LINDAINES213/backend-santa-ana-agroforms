from rest_framework.routers import DefaultRouter
from .views import FormularioViewSet, CampoViewSet

router = DefaultRouter()
router.register(r'formularios', FormularioViewSet)
# router.register(r'campos', CampoViewSet, basename='campo')


urlpatterns = router.urls