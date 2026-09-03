"""
Punto de entrada CLI para el operador de telemetría de Triton.

Responsabilidad:
Integrante 5 - Coordinador de Integración y Flujo CLI.
"""

import argparse
import asyncio
import logging
import sys

# =======================================================================
# IMPORTACIÓN POR FACHADA (Patrón Facade vía __init__.py)
# =======================================================================
from triton_telemetry import (
    ProviderTimeoutError,
    CorruptedPayloadError,
    NetworkPeeringError,
    scan_all_providers,
    setup_triton_observability,
    shutdown_triton_observability,
    validate_timeout,
    validate_cluster_id,
)


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de la aplicación."""
    parser = argparse.ArgumentParser(
        description="Operador CLI de telemetría Triton (Multicloud Async)"
    )

    parser.add_argument(
        "--mode",
        choices=["nominal", "debug", "emergency"],
        default="nominal",
        help="Modo operativo de la aplicación.",
    )

    # 1. Inyección de Validadores Estrictos (Responsabilidad Integrante 1)
    parser.add_argument(
        "--timeout",
        type=validate_timeout,
        default=2.0,
        help="Tiempo máximo de espera de red en segundos [Rango: 0.1 a 5.0].",
    )

    parser.add_argument(
        "--cluster",
        type=validate_cluster_id,
        required=False,
        help="Identificador opcional del clúster (Ej: cluster-us-east-01).",
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--quiet", action="store_true", help="Oculta mensajes de salida normales."
    )
    output_group.add_argument(
        "--verbose", action="store_true", help="Muestra información de depuración detallada."
    )

    return parser


async def main() -> None:
    """Punto de entrada asíncrono y orquestador principal."""
    parser = build_parser()
    args = parser.parse_args()

    # 1. Determinación dinámica del nivel de logs
    if args.quiet:
        log_level = logging.WARNING
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # 2. INICIALIZAR EL MOTOR DE LOGS (Responsabilidad Integrantes 3 y 4)
    logger = setup_triton_observability(level=log_level)

    logger.info("============================================================")
    logger.info("INICIANDO OPERADOR TRITON EN MODO: %s", args.mode.upper())
    if args.cluster:
        logger.info("Clúster Objetivo: %s", args.cluster)
    logger.info("============================================================")

    try:
        # 3. EJECUTAR EL ESCANEO CONCURRENTE (Responsabilidad Integrante 2)
        logger.info(f"Lanzando telemetría asíncrona (Timeout configurado: {args.timeout}s)...")

        # Le pasamos el timeout dinámico validado por argparse
        resultados = await scan_all_providers(timeout=args.timeout)

        logger.info("Escaneo nominal completado exitosamente. Nodos respondieron: %d", len(resultados))

    # =======================================================================
    # CAPTURA QUIRÚRGICA DE EXCEPTION GROUPS (Python 3.11+)
    # =======================================================================
    except* ProviderTimeoutError as group:
        logger.error("DETECTADOS FALLOS DE TIMEOUT (%d nodos afectados)", len(group.exceptions))
        for error in group.exceptions:
            logger.error("Detalle de latencia: %s", error)
            for note in getattr(error, "__notes__", []):
                logger.error(" - Contexto forense: %s", note)

    except* CorruptedPayloadError as group:
        logger.error("DETECTADOS PAYLOADS CORRUPTOS (%d nodos afectados)", len(group.exceptions))
        for error in group.exceptions:
            logger.error("Error de formato/status: %s", error)

    except* NetworkPeeringError as group:
        logger.critical("DETECTADA PÉRDIDA DE PEERING (%d errores críticos)", len(group.exceptions))
        for error in group.exceptions:
            logger.critical("Detalle de red: %s", error)

    finally:
        # 4. APAGADO DETERMINISTA (PEP 765)
        # Vacía la RAM al disco antes de que el script muera.
        logger.info("Finalizando operaciones. Vaciando colas de memoria a disco...")
        logger.info("============================================================")
        shutdown_triton_observability()


def cli() -> None:
    """Punto de entrada ejecutable desde la línea de comandos."""
    asyncio.run(main())


if __name__ == "__main__":
    # Previene el secuestro de dependencias en caliente si alguien llama el script de forma insegura
    if sys.path[0] == "":
        del sys.path[0]

    cli()
