import logging
import time
import json
from django.utils.deprecation import MiddlewareMixin

# Custom formatter para aplanar los campos
class CustomJsonFormatter(logging.Formatter):
    def format(self, record):
        # Si tiene el atributo custom, extraerlo
        custom = getattr(record, 'custom', {})
        
        log_data = {
            'asctime': self.formatTime(record),
            'name': record.name,
            'levelname': record.levelname,
            'message': record.getMessage(),
        }
        
        # Agregar campos custom al mismo nivel (sin el wrapper "custom")
        log_data.update(custom)
        
        return json.dumps(log_data)

logger = logging.getLogger('api')

class APILoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.start_time = time.time()
        
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = (time.time() - request.start_time) * 1000
            
            logger.info(
                "API Request",
                extra={
                    'custom': {
                        '@timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'http.request.method': request.method,
                        'http.response.status_code': response.status_code,
                        'event.duration': duration,
                        'url.path': request.path,
                        'service.name': 'formularios-api',
                        'log.level': 'INFO' if response.status_code < 400 else 'ERROR',
                        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                        'remote_addr': request.META.get('REMOTE_ADDR', ''),
                    }
                }
            )
            
        return response