# =============================================================================
# sql_service.py LIMPIO - Solo métodos necesarios
# REEMPLAZAR COMPLETO
# =============================================================================

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import re
import traceback


class SQLConnectionService:
    """
    Servicio para manejar conexiones dinámicas a bases de datos SQL externas
    """
    
    @staticmethod
    def crear_connection_string(conexion) -> str:
        """
        Crea el connection string basado en el tipo de BD
        """
        try:
            password = conexion.get_password()
        except Exception as e:
            raise ValueError(f"Error obteniendo password: {str(e)}")
        
        # Escapar caracteres especiales en password para URL
        from urllib.parse import quote_plus
        password_escaped = quote_plus(password)
        usuario_escaped = quote_plus(conexion.usuario)
        
        if conexion.tipo_bd == 'postgresql':
            return f"postgresql://{usuario_escaped}:{password_escaped}@{conexion.host}:{conexion.puerto}/{conexion.database}"
        
        elif conexion.tipo_bd == 'mysql':
            return f"mysql+pymysql://{usuario_escaped}:{password_escaped}@{conexion.host}:{conexion.puerto}/{conexion.database}"
        
        elif conexion.tipo_bd == 'sqlserver':
            driver = conexion.opciones_extra.get('driver', 'ODBC Driver 17 for SQL Server')
            driver_escaped = quote_plus(driver)
            return f"mssql+pyodbc://{usuario_escaped}:{password_escaped}@{conexion.host}:{conexion.puerto}/{conexion.database}?driver={driver_escaped}"
        
        elif conexion.tipo_bd == 'oracle':
            return f"oracle+cx_oracle://{usuario_escaped}:{password_escaped}@{conexion.host}:{conexion.puerto}/{conexion.database}"
        
        else:
            raise ValueError(f"Tipo de BD no soportado: {conexion.tipo_bd}")
    
    @staticmethod
    def probar_conexion(conexion) -> Tuple[bool, Optional[str]]:
        """
        Prueba la conexión a la base de datos
        Returns: (success, error_message)
        """
        try:
            connection_string = SQLConnectionService.crear_connection_string(conexion)
            engine = create_engine(
                connection_string,
                connect_args={'connect_timeout': 10},
                pool_pre_ping=True
            )
            
            # Intentar conectar y hacer un query simple
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            engine.dispose()
            return True, None
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return False, error_msg
    
    @staticmethod
    def validar_query(query_sql: str) -> Tuple[bool, Optional[str]]:
        """
        Valida que el query sea seguro (solo SELECT)
        Returns: (is_valid, error_message)
        """
        query_lower = query_sql.lower().strip()
        
        # Verificar que sea SELECT
        if not query_lower.startswith('select'):
            return False, "Solo se permiten queries SELECT"
        
        # Verificar que no contenga comandos peligrosos
        forbidden_keywords = [
            'drop', 'delete', 'truncate', 'insert', 'update',
            'alter', 'create', 'grant', 'revoke', 'exec',
            'execute', 'xp_', 'sp_', 'into outfile', 'load_file'
        ]
        
        for keyword in forbidden_keywords:
            # Usar word boundaries para evitar falsos positivos
            if re.search(rf'\b{keyword}\b', query_lower):
                return False, f"Palabra clave no permitida: {keyword}"
        
        # Verificar que no tenga múltiples statements
        query_stripped = query_sql.rstrip().rstrip(';')
        if ';' in query_stripped:
            return False, "No se permiten múltiples statements"
        
        return True, None
    
    @staticmethod
    def ejecutar_query(
        conexion, 
        query_sql: str, 
        limit: int = 1000
    ) -> Tuple[List[str], List[Dict], Optional[str]]:
        """
        Ejecuta un query en la conexión especificada
        Returns: (columnas, datos, error_message)
        """
        try:
            # Validar query
            is_valid, error = SQLConnectionService.validar_query(query_sql)
            if not is_valid:
                return [], [], error
            
            # Agregar LIMIT si no existe (y no es agregación/group by)
            query_lower = query_sql.lower()
            if 'limit' not in query_lower and 'top' not in query_lower:
                # Solo agregar LIMIT si no tiene GROUP BY o funciones de agregación
                if 'group by' not in query_lower and not any(x in query_lower for x in ['count(', 'sum(', 'avg(', 'max(', 'min(']):
                    query_sql = f"{query_sql} LIMIT {limit}"
            
            # Crear conexión
            try:
                connection_string = SQLConnectionService.crear_connection_string(conexion)
            except Exception as e:
                return [], [], f"Error creando connection string: {str(e)}"
            
            try:
                engine = create_engine(
                    connection_string,
                    connect_args={'connect_timeout': 30},
                    pool_pre_ping=True
                )
            except Exception as e:
                return [], [], f"Error conectando a BD: {str(e)}"
            
            # Ejecutar query
            try:
                df = pd.read_sql_query(query_sql, engine)
            except Exception as e:
                error_detail = f"Error ejecutando query: {str(e)}"
                return [], [], error_detail
            finally:
                engine.dispose()
            
            # Procesar resultados
            columnas = [str(col).strip() for col in df.columns]
            
            # Convertir tipos de datos para JSON
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                elif df[col].dtype == 'object':
                    try:
                        df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
            
            # Reemplazar NaN
            df = df.fillna('')
            
            # Convertir a lista de diccionarios
            datos = df.to_dict('records')
            
            # Limpieza adicional
            for row in datos:
                for key, value in row.items():
                    if pd.isna(value) or value is None:
                        row[key] = ''
                    elif not isinstance(value, (str, int, float, bool, list, dict)):
                        row[key] = str(value)
            
            return columnas, datos, None
            
        except Exception as e:
            error_detail = f"Error inesperado: {str(e)}\nTraceback: {traceback.format_exc()}"
            return [], [], error_detail