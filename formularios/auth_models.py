from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

class UsuarioManager(BaseUserManager):
    def create_user(self, nombre_usuario, correo, password=None, **extra_fields):
        if not correo:
            raise ValueError('El usuario debe tener un correo electrónico')
        
        correo = self.normalize_email(correo)
        user = self.model(nombre_usuario=nombre_usuario, correo=correo, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, nombre_usuario, correo, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('activo', True)
        
        return self.create_user(nombre_usuario, correo, password, **extra_fields)

# class UsuarioAuth(AbstractBaseUser, PermissionsMixin):
#     nombre_usuario = models.CharField(max_length=50, primary_key=True, unique=True)
#     nombre = models.CharField(max_length=100)
#     correo = models.EmailField(unique=True)
#     activo = models.BooleanField(default=True)
#     is_staff = models.BooleanField(default=False)
#     is_superuser = models.BooleanField(default=False)
    
#     roles = models.ManyToManyField(
#         "formularios.Rol",
#         through="formularios.RolUser",
#         related_name="usuarios_auth",
#     )

#     objects = UsuarioManager()

#     USERNAME_FIELD = 'nombre_usuario'
#     REQUIRED_FIELDS = ['correo', 'nombre']

#     class Meta:
#         db_table = "formularios_usuario"

#     def __str__(self):
#         return self.nombre_usuario

#     @property
#     def is_active(self):
#         return self.activo