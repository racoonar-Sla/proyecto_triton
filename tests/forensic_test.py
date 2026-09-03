"""
tests/forensic_test.py
Validador forense de NDJSON y de históricos .gz del Proyecto Tritón.

Uso:
    python tests/forensic_test.py
    python tests/forensic_test.py --log ruta/al/triton_services.log
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import datetime
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    """Evalúa una condición y lanza AssertionError si es falsa."""
    if not condition:
        raise AssertionError(message)


def find_log_files(log_path: Path) -> list[Path]:
    """Busca el log activo y sus históricos comprimidos."""
    files: list[Path] = []
    if log_path.exists():
        files.append(log_path)
    files.extend(sorted(log_path.parent.glob(f"{log_path.name}*.gz")))
    return files


def read_json_lines(path: Path) -> list[dict[str, Any]]:
    """Descomprime si corresponde y valida una línea NDJSON por registro."""
    opener = gzip.open if path.suffix == ".gz" else Path.open

    if path.suffix == ".gz":
        stream = opener(path, "rt", encoding="utf-8")
    else:
        stream = opener(path, "rt", encoding="utf-8")

    records: list[dict[str, Any]] = []
    with stream as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise AssertionError(
                    f"{path}:{line_number} no es JSON válido: {error}"
                ) from error

            require(
                isinstance(record, dict),
                f"{path}:{line_number} no contiene un objeto JSON.",
            )
            records.append(record)

    return records


def walk_tree(node: Any):
    """Recorre recursivamente objetos/listas del árbol de excepciones."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_tree(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_tree(item)


def validate_iso_utc(timestamp: Any, source: Path) -> None:
    """Valida que la marca de tiempo cumpla estrictamente con ISO 8601 UTC."""
    require(isinstance(timestamp, str), f"{source}: timestamp no es string.")
    require(timestamp.endswith("Z"), f"{source}: timestamp no termina en Z.")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise AssertionError(
            f"{source}: timestamp no es ISO 8601 válido: {timestamp}"
        ) from error


def validate_record(record: dict[str, Any], source: Path) -> None:
    """Valida campos mínimos de telemetría en cada registro NDJSON."""
    required = {"timestamp", "level", "logger", "message", "thread_name"}
    missing = sorted(required.difference(record))
    require(not missing, f"{source}: faltan campos: {missing}")
    validate_iso_utc(record["timestamp"], source)


def validate_gzip_files(files: list[Path]) -> list[Path]:
    """Certifica que todos los históricos .gz son legibles."""
    gz_files = [path for path in files if path.suffix == ".gz"]
    for path in gz_files:
        try:
            with gzip.open(path, "rb") as handle:
                handle.read(1024)
        except OSError as error:
            raise AssertionError(
                f"{path} no se puede descomprimir correctamente: {error}"
            ) from error
        print(f"[PASS] Gzip íntegro: {path.name}")
    return gz_files


def validate_exception_tree(records: list[dict[str, Any]]) -> None:
    """
    Busca y valida el árbol forense.

    La prueba exige exception_tree, notas y una causa. Si el grupo todavía no
    registra exc_info al usar logger.error(), esta prueba señalará la integración
    que falta en lugar de ocultarla.
    """
    trees = [record["exception_tree"] for record in records if record.get("exception_tree")]
    require(
        trees,
        "No apareció exception_tree. Verificá que el bloque except* registre "
        "la excepción con exc_info para que el formatter pueda serializarla.",
    )

    nodes = [node for tree in trees for node in walk_tree(tree)]
    classes = {node.get("class") for node in nodes if isinstance(node, dict)}
    require(classes, "exception_tree existe pero no contiene clases.")

    has_notes = any(
        isinstance(node.get("notes"), list) and node.get("notes")
        for node in nodes
        if isinstance(node, dict)
    )
    require(has_notes, "No se encontraron __notes__ dentro del árbol forense.")

    has_cause = any(
        isinstance(node, dict) and "cause" in node
        for node in nodes
    )
    require(has_cause, "No se encontró una causa encadenada mediante raise ... from.")

    print("[PASS] exception_tree, notes y cause presentes")


def validate_http_metadata(records: list[dict[str, Any]]) -> None:
    """
    Valida metadatos HTTP cuando el formatter los expone.

    No inventa un esquema obligatorio distinto al definido por el grupo:
    busca status_code, método o equivalente dentro del registro/árbol.
    """
    text = json.dumps(records, ensure_ascii=False).lower()
    has_status = bool(re.search(r"\bstatus(?:_code)?\b|http_status_code", text))
    has_http_error = any(
        any(
            marker in node.get("class", "")
            for marker in ("HTTPStatusError", "NetworkPeeringError", "CorruptedPayloadError")
        )
        for record in records
        for node in walk_tree(record.get("exception_tree", {}))
        if isinstance(node, dict)
    )

    require(
        has_status or has_http_error,
        "No se encontró evidencia de estatus HTTP ni de una excepción HTTP en los logs.",
    )
    print("[PASS] Evidencia de estatus/error HTTP encontrada")


def main() -> int:
    """Punto de entrada principal de la suite forense."""
    parser = argparse.ArgumentParser(description="Validador forense de logs Tritón.")
    parser.add_argument(
        "--log",
        type=Path,
        default=PROJECT_ROOT / "triton_services.log",
        help="Ruta al log principal.",
    )
    args = parser.parse_args()

    try:
        files = find_log_files(args.log)
        require(
            files,
            f"No se encontraron logs en {args.log}. Ejecutá primero la suite de caos.",
        )

        gz_files = validate_gzip_files(files)
        require(
            gz_files,
            "No se encontró ningún histórico .gz. Para esta prueba forense "
            "el sistema debe haber ejecutado al menos una rotación del log.",
        )

        all_records: list[dict[str, Any]] = []
        for path in files:
            records = read_json_lines(path)
            require(records, f"{path} existe pero está vacío.")
            for record in records:
                validate_record(record, path)
            all_records.extend(records)
            print(f"[PASS] NDJSON íntegro: {path.name} ({len(records)} registros)")

        validate_exception_tree(all_records)
        validate_http_metadata(all_records)
        print(f"[PASS] Registros forenses analizados: {len(all_records)}")
        print("\nRESULTADO FINAL: PASS")
        return 0

    except (AssertionError, OSError) as error:
        print(f"\nRESULTADO FINAL: FAIL\n{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
