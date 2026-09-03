"""
Excepciones semánticas para el sistema de telemetría multicloud.

Todas heredan de TritonError, que a su vez hereda de Exception
(NUNCA de BaseException) para no interferir con señales de sistema
como KeyboardInterrupt (Ctrl+C) o SystemExit.
"""


class TritonError(Exception):
    """Excepción base del sistema. Hereda de Exception, no de BaseException."""
    pass


class ProviderTimeoutError(TritonError):
    """Se produce cuando un proveedor no responde dentro del tiempo esperado
    (timeouts de red)."""
    pass


class CorruptedPayloadError(TritonError):
    """Se produce cuando la respuesta recibida está corrupta o el estatus
    HTTP indica un fallo."""
    pass


class NetworkPeeringError(TritonError):
    """Se produce ante fallos de DNS o de resolución de hosts."""
    pass
