"""Capa de dominio: value objects y errores propios, sin dependencias de I/O.

No importa gspread ni google-auth: define el vocabulario de Google Sheets (rangos,
formatos, reglas de validación) como objetos inmutables que serializan a la forma
JSON que espera la API. El transporte vive en la capa de infraestructura.
"""
