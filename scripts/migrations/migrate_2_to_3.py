#!/usr/bin/env python3
# python-file: script
"""Migration of a measurement from version 2 to version 3 (SDLC-0042, SDLC-0043).

Version 3 replaces the one agent of version 2 with a list of agents, each with
the model it ran on, and is stored as a YAML file.

    ./scripts/migrations/migrate_2_to_3.py <path> [--carry-gaps <path>] [--apply]

Version 2 did not record the model, so the one agent it names becomes the only
entry of the list with the model "nieznany" — and that is recorded as a gap.
The name of the file keeps its stem and changes its extension to .yaml.

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kinds
import migration

SOURCE = 2
TARGET = 3
UNKNOWN_MODEL = "nieznany"
ORDER = ("schema_version", "uid", "protocol", "name", "project", "agents",
         "description", "interactions", "corrections", "measurements",
         "migration_gaps", "started", "finished", "run_id")


def transform(document: Dict[str, object], gaps: List[Dict[str, object]],
              path: Path) -> Dict[str, object]:
    """Measurement of version 2, carried over to version 3."""
    result = dict(document)
    result["schema_version"] = TARGET
    agent = result.pop("agent")
    result["agents"] = [{"name": agent["name"], "model": UNKNOWN_MODEL,
                         "sessions": list(agent["sessions"])}]
    gaps.append(migration.gap(
        "agents.model", SOURCE,
        "wersja 2 nie zapisywała modelu; wpisano {}".format(UNKNOWN_MODEL)))
    # Version 2 stores its gaps, and the chain hands the same ones over again.
    stored = list(result.get("migration_gaps") or [])
    result["migration_gaps"] = stored + [entry for entry in gaps if entry not in stored]
    return {key: result[key] for key in ORDER if key in result}


def name(document: Dict[str, object], path: Path) -> str:
    """File name of version 3: the stem of version 2, as a YAML file."""
    return path.stem + kinds.suffix_for(kinds.PROCESS_KIND, TARGET)


if __name__ == "__main__":
    sys.exit(migration.main(sys.argv, Path(__file__), SOURCE, TARGET, transform, name))
