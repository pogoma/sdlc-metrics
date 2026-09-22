#!/usr/bin/env python3
# python-file: script
"""Migration of a performance measurement from version 1 to version 2 (SDLC-0042).

Version 2 has the shape of version 1 and is stored as a YAML file.

    ./scripts/migrations/migrate_performance_1_to_2.py <path> [--apply]

Nothing is lost on the way, so the step records no gap. The name of the file
keeps its stem and changes its extension to .yaml.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kinds
import migration

SOURCE = 1
TARGET = 2


def transform(document: Dict[str, object], gaps: List[Dict[str, object]],
              path: Path) -> Dict[str, object]:
    """Measurement of version 1, carried over to version 2."""
    result = dict(document)
    result["schema_version"] = TARGET
    # Version 1 stores its gaps, and the chain hands the same ones over again.
    stored = list(result.get("migration_gaps") or [])
    result["migration_gaps"] = stored + [entry for entry in gaps if entry not in stored]
    return result


def name(document: Dict[str, object], path: Path) -> str:
    """File name of version 2: the stem of version 1, as a YAML file."""
    return path.stem + kinds.suffix_for(kinds.PERFORMANCE_KIND, TARGET)


if __name__ == "__main__":
    sys.exit(migration.main(sys.argv, Path(__file__), SOURCE, TARGET, transform, name,
                            kinds.PERFORMANCE_KIND))
