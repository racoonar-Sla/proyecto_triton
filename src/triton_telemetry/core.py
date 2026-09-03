"""
Módulo de telemetría asíncrona concurrente.
Orquesta múltiples peticiones a proveedores cloud utilizando httpx y asyncio.TaskGroup.
"""
import asyncio
import httpx
from triton_telemetry.exceptions import CorruptedPayloadError, ProviderTimeoutError


async def fetch_aws(client: httpx.AsyncClient) -> dict:
    """Consulta nominal para el estado de AWS."""
    response = await client.get("https://jsonplaceholder.typicode.com/posts/1")
    response.raise_for_status()
    return response.json()


async def fetch_azure(client: httpx.AsyncClient) -> dict:
    """Consulta nominal para el estado de Azure."""
    response = await client.get("https://jsonplaceholder.typicode.com/posts/2")
    response.raise_for_status()
    return response.json()


async def fetch_gcp(client: httpx.AsyncClient) -> dict:
    """Consulta nominal para el estado de GCP."""
    response = await client.get("https://jsonplaceholder.typicode.com/posts/3")
    response.raise_for_status()
    return response.json()


async def fetch_with_timeout_trigger(client: httpx.AsyncClient, timeout: float) -> dict:
    """Simula una consulta con alta latencia para gatillar ProviderTimeoutError."""
    try:
        response = await client.get("https://httpbin.org/delay/3", timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as err:
        custom_err = ProviderTimeoutError(f"Timeout de red superado ({timeout}s)")
        custom_err.add_note("Timeout superado en el nodo de telemetría de respaldo")
        raise custom_err from err


async def fetch_with_status_trigger(client: httpx.AsyncClient) -> dict:
    """Simula respuestas HTTP de error para gatillar CorruptedPayloadError."""
    try:
        response = await client.get("https://httpbin.org/status/504")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as err:
        raise CorruptedPayloadError("Estatus HTTP no esperado recibido de la API") from err


async def scan_all_providers(timeout: float = 2.0) -> list[dict]:
    """Orquesta las consultas asíncronas concurrentes usando asyncio.TaskGroup."""
    async with httpx.AsyncClient() as client:
        async with asyncio.TaskGroup() as tg:
            # 1. Peticiones nominales reales (AWS, Azure, GCP)
            task_aws = tg.create_task(fetch_aws(client))
            task_azure = tg.create_task(fetch_azure(client))
            task_gcp = tg.create_task(fetch_gcp(client))

            # 2. Inyección de caos controlado para pruebas de resiliencia
            task_timeout = tg.create_task(fetch_with_timeout_trigger(client, timeout))
            task_status = tg.create_task(fetch_with_status_trigger(client))

        # El bloque 'async with' garantiza que esperamos a que TODAS terminen
        # antes de continuar. Luego devolvemos los resultados (si no fallaron).
        return [
            task_aws.result(),
            task_azure.result(),
            task_gcp.result(),
            task_timeout.result(),
            task_status.result()
        ]
