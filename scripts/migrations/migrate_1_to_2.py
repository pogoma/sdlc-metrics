#!/usr/bin/env python3
"""Migration of a measurement from version 1 to version 2 (SDLC-0013).

Version 2 adds three fields to version 1: the schema version in the content,
the identifier of the protocol call and a place for gaps left by migration.

    ./scripts/migrations/migrate_1_to_2.py <path> [--carry-gaps <path>] [--apply]

Version 1 had no identifier of the call, so the one this step writes is minted
here, not recovered — and that is recorded as a gap. The name of the file
changes with the version: <stamp>-<project>-<uid>.json.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migration

SOURCE = 1
TARGET = 2
ORDER = ("schema_version", "uid", "protocol", "name", "project", "agent",
         "description", "interactions", "corrections", "measurements",
         "migration_gaps", "started", "finished", "run_id")


def transform(document: Dict[str, object], gaps: List[Dict[str, object]],
              path: Path) -> Dict[str, object]:
    """Measurement of version 1, carried over to version 2."""
    result = dict(document)
    result["schema_version"] = TARGET
    result["uid"] = migration.new_uid()
    gaps.append(migration.gap(
        "uid", SOURCE,
        "wersja 1 nie miała identyfikatora wywołania; nadany przy migracji"))
    if "finished" not in result:
        gaps.append(migration.gap(
            "finished", SOURCE,
            "pomiar nie podawał czasu zamknięcia; nazwa pliku bierze znacznik "
            "z nazwy pliku źródłowego"))
    result["migration_gaps"] = list(gaps)
    return {key: result[key] for key in ORDER if key in result}


def name(document: Dict[str, object], path: Path) -> str:
    """File name of version 2: <stamp>-<project>-<uid>.json."""
    stamp = migration.stamp_of(document, path) or "00000000T000000Z"
    return "{}-{}-{}.json".format(stamp, document.get("project"), document.get("uid"))


if __name__ == "__main__":
    sys.exit(migration.main(sys.argv, Path(__file__), SOURCE, TARGET, transform, name))
