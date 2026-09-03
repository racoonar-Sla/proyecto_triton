"""
API Pública del paquete triton_telemetry (Patrón Fachada).
Expone de forma centralizada las herramientas de monitoreo multicloud.
"""

# Importaciones relativas internas (usando el punto '.')
from .exceptions import (
    TritonError,
    ProviderTimeoutError,
    CorruptedPayloadError,
    NetworkPeeringError,
)
from .sanitizer import validate_timeout, validate_cluster_id
from .core import scan_all_providers
from .logging_engine import setup_triton_observability, shutdown_triton_observability

# Contrato explícito de la API pública
__all__ = [
    "TritonError",
    "ProviderTimeoutError",
    "CorruptedPayloadError",
    "NetworkPeeringError",
    "validate_timeout",
    "validate_cluster_id",
    "scan_all_providers",
    "setup_triton_observability",
    "shutdown_triton_observability",
]
