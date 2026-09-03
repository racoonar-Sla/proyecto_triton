"""
tests/chaos_test.py
Suite de Simulación de Caos e Integración para Proyecto Tritón.

Ejecutar desde la raíz del proyecto:
    python tests/chaos_test.py

Opcional:
    python tests/chaos_test.py --runs 12 --workers 4

La suite usa únicamente la biblioteca estándar. Ejecuta la CLI real como
procesos independientes para validar el comportamiento concurrente del sistema.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = PROJECT_ROOT / "src" / "app_operator.py"


def require(condition: bool, message: str) -> None:
    """Evalúa una condición y lanza AssertionError si es falsa."""
    if not condition:
        raise AssertionError(message)


def run_cli(
    app_path: Path,
    *args: str,
    timeout_process: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Ejecuta la CLI real como un proceso hijo."""
    command = [sys.executable, str(app_path), *args]
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_process,
        check=False,
    )


def test_cli_timeout(app_path: Path) -> None:
    """Fuerza el escenario de timeout real mediante --chaos y --timeout 0.1."""
    result = run_cli(
        app_path,
        "AWS",
        "-c",
        "cluster-us-east-01",
        "-t",
        "0.1",
        "--chaos",
    )
    output = f"{result.stdout}\n{result.stderr}".lower()

    require(
        result.returncode == 0,
        f"La CLI terminó con código {result.returncode}.\n{output}",
    )
    require(
        "timeout" in output or "tiempo de espera" in output,
        "No se encontró evidencia del timeout en la salida de la CLI.",
    )
    print("[PASS] Timeout real controlado")


def test_multi_provider_chaos(app_path: Path) -> None:
    """Ejecuta AWS/Azure/GCP en la misma invocación para probar TaskGroup."""
    result = run_cli(
        app_path,
        "AWS",
        "Azure",
        "GCP",
        "-c",
        "cluster-us-west-02",
        "-t",
        "1.5",
        "--chaos",
    )
    output = f"{result.stdout}\n{result.stderr}".lower()

    require(
        result.returncode == 0,
        f"La CLI terminó con código {result.returncode}.\n{output}",
    )
    require(
        any(token in output for token in ("timeout", "504", "gateway", "corrupt", "payload")),
        "No apareció evidencia de un fallo de caos en la salida.",
    )
    print("[PASS] Escenario multicloud concurrente")


def test_massive_cli_concurrency(
    app_path: Path,
    runs: int,
    workers: int,
) -> None:
    """
    Ejecuta muchas instancias reales de app_operator.py en paralelo.

    Esta es la prueba principal de estrés del Integrante 6: busca demostrar que
    múltiples procesos pueden generar telemetría y errores sin provocar un
    crash ni quedarse bloqueados.
    """
    require(runs >= 4, "--runs debe ser >= 4.")
    require(1 <= workers <= runs, "--workers debe estar entre 1 y --runs.")

    scenarios = []
    for index in range(runs):
        if index % 3 == 0:
            scenarios.append(
                (
                    "AWS",
                    "-c",
                    f"cluster-us-east-{index % 90 + 10:02d}",
                    "-t",
                    "0.1",
                    "--chaos",
                )
            )
        elif index % 3 == 1:
            scenarios.append(
                (
                    "AWS",
                    "Azure",
                    "GCP",
                    "-c",
                    f"cluster-us-west-{index % 90 + 10:02d}",
                    "-t",
                    "1.5",
                    "--chaos",
                )
            )
        else:
            scenarios.append(
                (
                    "AWS",
                    "GCP",
                    "-c",
                    f"cluster-eu-west-{index % 90 + 10:02d}",
                    "-t",
                    "3.0",
                )
            )

    def worker(args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        """Ejecuta una instancia individual de la CLI en el pool de hilos."""
        return run_cli(app_path, *args, timeout_process=45.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, scenario) for scenario in scenarios]
        results = [future.result() for future in futures]

    failed = [
        (index + 1, result.returncode, result.stdout, result.stderr)
        for index, result in enumerate(results)
        if result.returncode != 0
    ]

    require(
        not failed,
        "Una o más ejecuciones concurrentes terminaron con error:\n"
        + "\n".join(
            f"  #{index}: rc={code}\n{stdout}\n{stderr}"
            for index, code, stdout, stderr in failed
        ),
    )

    print(
        f"[PASS] Estrés de CLI: {runs} ejecuciones concurrentes con {workers} workers"
    )


def test_dns_failure() -> None:
    """
    Prueba el mapeo de un host inexistente a NetworkPeeringError.

    Se ejecuta directamente contra core.py porque la plantilla original de la
    CLI no expone una opción --endpoint para inyectar un host personalizado.
    """
    import asyncio

    async def trigger() -> None:
        """Gatilla el fallo de red inyectando un host inválido."""
        from triton_telemetry import core
        from triton_telemetry.exceptions import NetworkPeeringError

        original_url = core.PROVIDER_ENDPOINTS["AWS"]
        core.PROVIDER_ENDPOINTS["AWS"] = (
            "https://triton-host-que-no-existe.invalid/"
        )
        try:
            try:
                await core.query_provider_telemetry("AWS", timeout=2.0)
            except NetworkPeeringError as error:
                notes = getattr(error, "__notes__", [])
                require(
                    "Provider_ID: AWS" in notes,
                    "NetworkPeeringError perdió la nota Provider_ID.",
                )
                return
            raise AssertionError(
                "El host inexistente no produjo NetworkPeeringError."
            )
        finally:
            core.PROVIDER_ENDPOINTS["AWS"] = original_url

    asyncio.run(trigger())
    print("[PASS] Host inexistente / fallo de red")


def main() -> int:
    """Punto de entrada principal de la suite de caos."""
    parser = argparse.ArgumentParser(description="Suite de caos del Proyecto Tritón.")

    # 1. Ruta al orquestador principal
    parser.add_argument(
        "--app",
        type=Path,
        default=DEFAULT_APP,
        help="Ruta a src/app_operator.py.",
    )

    # 2. Cantidad de simulaciones totales a inyectar
    parser.add_argument(
        "--runs",
        type=int,
        default=12,
        help="Cantidad de procesos CLI concurrentes para la prueba de estrés.",
    )

    # 3. Cantidad de workers en paralelo
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Cantidad de workers concurrentes para ejecutar la CLI.",
    )

    args = parser.parse_args()

    try:
        require(args.app.exists(), f"No existe la CLI: {args.app}")

        print("=== PROYECTO TRITÓN: CHAOS TEST ===")
        test_cli_timeout(args.app)
        test_multi_provider_chaos(args.app)
        test_massive_cli_concurrency(args.app, args.runs, args.workers)
        test_dns_failure()
        print("\nRESULTADO FINAL: PASS")
        return 0

    except (AssertionError, subprocess.TimeoutExpired) as error:
        print(f"\nRESULTADO FINAL: FAIL\n{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
