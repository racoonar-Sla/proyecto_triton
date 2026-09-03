"""
Validadores/sanitizadores para argumentos de la CLI.

Ambas funciones están pensadas para usarse como `type=` en argparse,
de modo que un valor inválido provoque un argparse.ArgumentTypeError
y la CLI termine limpiamente con código de salida 2.
"""

import argparse
import re

# cluster-<region>-<numero>, ej: cluster-us-east-01
_CLUSTER_PATTERN = re.compile(r'^cluster-[a-z]+(?:-[a-z]+)*-\d+$')

TIMEOUT_MIN = 0.1
TIMEOUT_MAX = 5.0


def validate_timeout(value):
    """
    Valida que --timeout sea un float dentro del rango [0.1, 5.0].

    Lanza argparse.ArgumentTypeError si el valor no es numérico o
    está fuera de rango, para que argparse detenga la ejecución
    con código de salida 2.
    """
    try:
        timeout = float(value)
    except (TypeError, ValueError) as err:
        raise argparse.ArgumentTypeError(
            f"'{value}' no es un valor numérico válido para --timeout"
        ) from err

    if not (TIMEOUT_MIN <= timeout <= TIMEOUT_MAX):
        raise argparse.ArgumentTypeError(
            f"--timeout debe estar entre {TIMEOUT_MIN} y {TIMEOUT_MAX} "
            f"segundos (recibido: {timeout})"
        )

    return timeout


def validate_cluster_id(value):
    """
    Valida que el identificador de clúster (opcional) siga el patrón
    estricto cluster-<region>-<numero>, ej: cluster-us-east-01.

    Lanza argparse.ArgumentTypeError si no coincide con el patrón.
    """
    if not _CLUSTER_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            f"'{value}' no cumple el patrón esperado "
            f"'cluster-<region>-<numero>' (ej.: cluster-us-east-01)"
        )

    return value
