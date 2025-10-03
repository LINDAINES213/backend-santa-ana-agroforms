from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from oauth2_provider.models import AccessToken, RefreshToken, Application
from oauthlib.common import generate_token
from django.utils import timezone
from datetime import timedelta
from .services import verify_password
from .models import Usuario

def _json_error(message, http_status):
    # Estructura consistente para cualquier error
    return Response(
        {"ok": False, "error": {"message": message}},
        status=http_status
    )

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Login para WEB — solo usuarios con acceso_web=True
    """
    nombre_usuario = (request.data.get('nombre_usuario') or "").strip()
    password = request.data.get('password') or ""

    if not nombre_usuario or not password:
        return _json_error("nombre_usuario y password son requeridos", status.HTTP_400_BAD_REQUEST)

    try:
        # 1) buscar usuario
        try:
            usuario = Usuario.objects.get(nombre_usuario=nombre_usuario)
        except Usuario.DoesNotExist:
            # Misma respuesta para usuario inexistente o password incorrecto (no revelar información)
            return _json_error("Credenciales inválidas", status.HTTP_401_UNAUTHORIZED)

        # 2) reglas de acceso antes de validar credenciales
        if not bool(usuario.activo):
            return _json_error("Usuario inactivo", status.HTTP_403_FORBIDDEN)

        # BLOQUEA acceso a la web si el flag no es True
        if bool(usuario.acceso_web) is not True:
            return _json_error(
                "Este usuario no tiene acceso a la plataforma web. Use la aplicación móvil.",
                status.HTTP_403_FORBIDDEN
            )

        # 3) validar contraseña (protegido ante hashes corruptos/plaintext)
        try:
            if not verify_password(usuario.password, password):
                return _json_error("Credenciales inválidas", status.HTTP_401_UNAUTHORIZED)
        except Exception:
            # Si el hash está en formato inesperado o corrupto, evita 500
            return _json_error("Credenciales inválidas", status.HTTP_401_UNAUTHORIZED)

        # 4) obtener/crear app OAuth2
        app, _ = Application.objects.get_or_create(
            name='Default App',
            defaults={
                'client_type': Application.CLIENT_CONFIDENTIAL,
                'authorization_grant_type': Application.GRANT_PASSWORD,
            }
        )

        # 5) revocar tokens previos de ESTE usuario (opcional: y de esta app)
        AccessToken.objects.filter(user=usuario).delete()
        RefreshToken.objects.filter(user=usuario).delete()

        # 6) emitir nuevos tokens
        expires = timezone.now() + timedelta(seconds=36000)
        access_token = AccessToken.objects.create(
            user=usuario,
            token=generate_token(),
            application=app,
            expires=expires,
            scope='read write'
        )
        refresh_token = RefreshToken.objects.create(
            user=usuario,
            token=generate_token(),
            application=app,
            access_token=access_token
        )

        # 7) payload de respuesta
        acceso_web = bool(usuario.acceso_web)


        return Response({
            "ok": True,
            "access_token": access_token.token,
            "refresh_token": refresh_token.token,
            "token_type": "Bearer",
            "expires_in": 36000,
            "scope": "read write",
            "user": {
                "nombre_usuario": usuario.nombre_usuario,
                "nombre": usuario.nombre,
                "correo": usuario.correo,
                "acceso_web": acceso_web
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        # No filtrar stacktrace al cliente; mensaje genérico y 500 controlado
        return _json_error("Error interno al procesar el login", status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def logout(request):
    """
    Endpoint de logout
    POST /api/auth/logout/
    Header: Authorization: Bearer <token>
    """
    try:
        token = request.auth
        if token:
            token.delete()
            return Response({'message': 'Logout exitoso'})
        return Response(
            {'error': 'No hay token activo'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def user_info(request):
    """
    Obtener información del usuario autenticado
    GET /api/auth/me/
    Header: Authorization: Bearer <token>
    """
    user = request.user
    # BIEN:
    acceso_web = bool(user.acceso_web)

    
    return Response({
        'nombre_usuario': user.nombre_usuario,
        'nombre': user.nombre,
        'correo': user.correo,
        'activo': user.activo,
        'acceso_web': user.acceso_web,
        'acceso_web': acceso_web
    })