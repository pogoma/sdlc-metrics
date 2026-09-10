#!/usr/bin/env python3
"""Migration of a measurement from version 0 to version 1 (SDLC-0013).

Version 0 is what the metrics repository held before the shape was settled:
a project, the name of the path of protocols taken, the identifier of the
commit and the quantities. Version 1 wants more than that, and most of it is
simply not in the file — so this step fills those fields with a stated
placeholder and records each one as a gap.

    ./scripts/migrations/migrate_0_to_1.py <path> [--carry-gaps <path>] [--apply]

Version 1 has nowhere to keep gaps, so they travel in the report and the step
to version 2 stores them. Running this migration alone leaves them in the
report only.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migration

SOURCE = 0
TARGET = 1
PROCESS_NAME = re.compile(r"^protokol-([a-z0-9]+(?:-[a-z0-9]+)*)$")
UNKNOWN_PROTOCOL = "NIEZNANY"
UNKNOWN_NAME = "nieznana ścieżka protokołów"
UNKNOWN_AGENT = "nieznany"
UNKNOWN_SESSION = "nieznana"
PLACEHOLDER_DESCRIPTION = "Pomiar sprzed ustalenia wzorca; opis przebiegu nie istnieje."
ORDER = ("protocol", "name", "project", "agent", "description", "interactions",
         "corrections", "measurements", "started", "finished", "run_id")


def protocol_of(process: object) -> str:
    """Protocol identifier read out of the name of the path taken, when it is there."""
    if isinstance(process, str):
        match = PROCESS_NAME.match(process.strip())
        if match:
            return match.group(1).upper()
    return UNKNOWN_PROTOCOL


def transform(document: Dict[str, object], gaps: List[Dict[str, object]],
              path: Path) -> Dict[str, object]:
    """Measurement of version 0, carried over to version 1."""
    process = document.get("process")
    protocol = protocol_of(process)
    if protocol == UNKNOWN_PROTOCOL:
        gaps.append(migration.gap(
            "protocol", SOURCE,
            "z pola process nie da się odczytać protokołu; wpisano {}".format(
                UNKNOWN_PROTOCOL)))
    result: Dict[str, object] = {
        "protocol": protocol,
        "name": process if isinstance(process, str) and process.strip() else UNKNOWN_NAME,
        "project": document.get("project"),
        "agent": {"name": UNKNOWN_AGENT, "sessions": [UNKNOWN_SESSION]},
        "description": PLACEHOLDER_DESCRIPTION,
        "interactions": 0,
        "corrections": [],
        "measurements": document.get("measurements", {}),
    }
    gaps.append(migration.gap("agent", SOURCE,
                              "wersja 0 nie zapisywała agenta ani sesji"))
    gaps.append(migration.gap("description", SOURCE,
                              "wersja 0 nie zapisywała opisu przebiegu"))
    gaps.append(migration.gap(
        "interactions", SOURCE,
        "wersja 0 nie liczyła wymian z człowiekiem; wpisano 0, a nie zmierzono"))
    gaps.append(migration.gap(
        "corrections", SOURCE,
        "wersja 0 nie zapisywała poprawek; lista jest pusta, a nie pusta z pomiaru"))
    if "run_id" in document:
        result["run_id"] = document["run_id"]
    stamp = migration.stamp_of({}, path)
    if stamp:
        result["finished"] = stamp
        gaps.append(migration.gap(
            "finished", SOURCE,
            "wersja 0 nie zapisywała czasu; znacznik wzięty z nazwy pliku źródłowego"))
    else:
        gaps.append(migration.gap(
            "finished", SOURCE,
            "wersja 0 nie zapisywała czasu, a nazwa pliku nie ma znacznika"))
    return {key: result[key] for key in ORDER if key in result}


def name(document: Dict[str, object], path: Path) -> str:
    """File name of version 1: <project>-<protokół>-<znacznik>.json."""
    stamp = migration.stamp_of(document, path) or "00000000T000000Z"
    return "{}-{}-{}.json".format(document.get("project"), document.get("protocol"),
                                  stamp)


if __name__ == "__main__":
    sys.exit(migration.main(sys.argv, Path(__file__), SOURCE, TARGET, transform, name))
