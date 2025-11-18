"""
Middleware para logging estructurado de requests HTTP en Django
Compatible con el stack ELK para monitoreo

Campos capturados:
- @timestamp
- http.request.method
- http.response.status_code
- event.duration
- url.path
- service.name
- log.level
"""

import logging
import time
import json
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('api.requests')


class ELKLoggingMiddleware(MiddlewareMixin):
    """
    Middleware que captura automáticamente cada request/response
    y genera logs estructurados en formato JSON para ELK Stack
    """
    
    def process_request(self, request):
        """Guarda el timestamp de inicio del request"""
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """
        Genera el log estructurado después de procesar el request
        """
        # Calcular duración en milisegundos
        duration_ms = 0
        if hasattr(request, '_start_time'):
            duration_ms = (time.time() - request._start_time) * 1000
        
        # Determinar log level basado en status code
        status_code = response.status_code
        if status_code >= 500:
            log_level = 'error'
            log_method = logger.error
        elif status_code >= 400:
            log_level = 'warning'
            log_method = logger.warning
        else:
            log_level = 'info'
            log_method = logger.info
        
        # Estructura del log con todos los campos requeridos
        log_data = {
            # Campo requerido 1: @timestamp (automático con python-json-logger)
            'http': {
                'request': {
                    'method': request.method,  # Campo requerido 2
                },
                'response': {
                    'status_code': status_code,  # Campo requerido 3
                }
            },
            'event': {
                'duration': round(duration_ms, 2),  # Campo requerido 4 (en ms)
            },
            'url': {
                'path': request.path,  # Campo requerido 5
                'full': request.build_absolute_uri(),
            },
            'service': {
                'name': 'santa-ana-agroforms-api',  # Campo requerido 6
            },
            'log': {
                'level': log_level,  # Campo requerido 7
            },
            # Campos adicionales útiles para monitoreo
            'user': {
                'nombre_usuario': request.user.nombre_usuario if request.user.is_authenticated else 'anonymous',
            },
            'client': {
                'ip': self._get_client_ip(request),
            },
            'request': {
                'query_params': dict(request.GET),
                'content_type': request.content_type,
            }
        }
        
        # Agregar información de errores si aplica
        if status_code >= 400:
            log_data['error'] = {
                'status_code': status_code,
                'path': request.path,
            }
        
        # Log el evento
        log_method(
            f"{request.method} {request.path} - {status_code}",
            extra={'log_data': log_data}
        )
        
        return response
    
    def _get_client_ip(self, request):
        """Obtiene la IP real del cliente considerando proxies"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def process_exception(self, request, exception):
        """Captura excepciones no manejadas"""
        duration_ms = 0
        if hasattr(request, '_start_time'):
            duration_ms = (time.time() - request._start_time) * 1000
        
        log_data = {
            'http': {
                'request': {
                    'method': request.method,
                },
                'response': {
                    'status_code': 500,
                }
            },
            'event': {
                'duration': round(duration_ms, 2),
            },
            'url': {
                'path': request.path,
            },
            'service': {
                'name': 'santa-ana-agroforms-api',
            },
            'log': {
                'level': 'error',
            },
            'error': {
                'type': type(exception).__name__,
                'message': str(exception),
                'stack_trace': True,
            },
            'client': {
                'ip': self._get_client_ip(request),
            }
        }
        
        logger.error(
            f"EXCEPTION: {request.method} {request.path} - {type(exception).__name__}: {str(exception)}",
            extra={'log_data': log_data},
            exc_info=True
        )
        
        return None
